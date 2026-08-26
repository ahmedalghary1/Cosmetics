from decimal import Decimal

from django.contrib.auth import authenticate, get_user_model
from django.core import mail
from django.core.cache import cache
from django.test import TestCase, override_settings
from django.urls import reverse

from core.models import StoreSettings
from products.models import Category, Product

from .forms import ProfileForm, RegistrationForm
from .models import Profile, WishlistItem


@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
class AccountTests(TestCase):
    def setUp(self):
        cache.clear()

    def registration_data(self, phone="010 1234 5678"):
        return {
            "full_name": "عميل تجريبي",
            "phone": phone,
            "email": "customer@example.com",
            "password1": "Complex-password-984!",
            "password2": "Complex-password-984!",
        }

    def test_registration_normalizes_unique_phone(self):
        form = RegistrationForm(self.registration_data())
        self.assertTrue(form.is_valid(), form.errors)
        user = form.save()
        self.assertEqual(user.username, "01012345678")
        self.assertEqual(user.profile.normalized_phone, "01012345678")
        duplicate = RegistrationForm(self.registration_data(phone="+20 101 234 5678"))
        self.assertFalse(duplicate.is_valid())
        self.assertIn("phone", duplicate.errors)

    def test_authentication_accepts_formatted_phone(self):
        user = get_user_model().objects.create_user(username="customer-login", password="safe-password-123")
        profile = user.profile
        profile.phone = "01012345678"
        profile.save()
        authenticated = authenticate(username="+20 101 234 5678", password="safe-password-123")
        self.assertEqual(authenticated, user)

    def test_profile_phone_change_updates_phone_username_atomically(self):
        user = get_user_model().objects.create_user(username="01012345678", password="safe-password-123")
        profile = user.profile
        profile.phone = "01012345678"
        profile.save()
        form = ProfileForm({
            "full_name": "اسم جديد", "phone": "011 2222 3333", "email": "new@example.com",
        }, user=user)
        self.assertTrue(form.is_valid(), form.errors)
        form.save()
        user.refresh_from_db()
        user.profile.refresh_from_db()
        self.assertEqual(user.username, "01122223333")
        self.assertEqual(user.profile.normalized_phone, "01122223333")

    def test_password_reset_email_uses_store_brand(self):
        get_user_model().objects.create_user(
            username="reset-user", email="reset@example.com", password="safe-password-123",
        )
        settings = StoreSettings.load()
        settings.store_name = "متجر الاختبار"
        settings.save()
        response = self.client.post(reverse("accounts:password_reset"), {"email": "reset@example.com"})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn("متجر الاختبار", mail.outbox[0].body)
        self.assertIn("/account/password-reset/", mail.outbox[0].body)
        self.assertIn("إذا لم يصدر هذا الطلب منك", mail.outbox[0].body)
        self.assertNotIn("تطلبي", mail.outbox[0].body)
        self.assertEqual(mail.outbox[0].subject, "استعادة كلمة المرور | متجر الاختبار")

    @override_settings(EMAIL_BACKEND="django.core.mail.backends.console.EmailBackend")
    def test_password_reset_does_not_report_success_with_console_backend(self):
        response = self.client.post(
            reverse("accounts:password_reset"),
            {"email": "customer@example.com"},
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "خدمة إرسال البريد غير مهيأة حاليًا")

    def test_inactive_products_are_hidden_from_wishlist(self):
        user = get_user_model().objects.create_user(username="wish", password="safe-password-123")
        category = Category.objects.create(name="البشرة")
        product = Product.objects.create(
            name="منتج", sku="WISH-1", category=category, description="x",
            price=Decimal("10"), stock_quantity=1, is_active=False,
        )
        WishlistItem.objects.create(user=user, product=product)
        self.client.force_login(user)
        response = self.client.get(reverse("accounts:wishlist"))
        self.assertEqual(list(response.context["wishlist_items"]), [])

    def test_login_rate_limit_returns_429(self):
        url = reverse("accounts:login")
        for _ in range(10):
            self.client.post(url, {"username": "missing", "password": "bad"})
        self.assertEqual(self.client.post(url, {"username": "missing", "password": "bad"}).status_code, 429)
