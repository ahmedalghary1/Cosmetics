from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse


@override_settings(SECURE_SSL_REDIRECT=False)
class DashboardPermissionTests(TestCase):
    def test_anonymous_user_is_redirected(self):
        response = self.client.get(reverse("dashboard:home"))
        self.assertEqual(response.status_code, 302)

    def test_regular_user_cannot_access_dashboard(self):
        user = get_user_model().objects.create_user(username="01000000001", password="safe-password")
        self.client.force_login(user)
        response = self.client.get(reverse("dashboard:home"))
        self.assertEqual(response.status_code, 403)

    def test_staff_user_can_access_dashboard(self):
        user = get_user_model().objects.create_user(
            username="admin-test", password="safe-password", is_staff=True
        )
        self.client.force_login(user)
        response = self.client.get(reverse("dashboard:home"))
        self.assertEqual(response.status_code, 200)

    def test_staff_management_pages_render(self):
        user = get_user_model().objects.create_user(
            username="manager-test", password="safe-password", is_staff=True
        )
        self.client.force_login(user)
        urls = [
            "home", "products", "product_add", "inventory", "categories", "category_add",
            "orders", "payments", "users", "shipping", "shipping_add", "coupons", "coupon_add",
            "banners", "banner_add", "pages", "page_add", "gallery", "gallery_add",
            "routine", "routine_add", "settings", "messages",
        ]
        for name in urls:
            with self.subTest(name=name):
                response = self.client.get(reverse(f"dashboard:{name}"))
                self.assertEqual(response.status_code, 200)
