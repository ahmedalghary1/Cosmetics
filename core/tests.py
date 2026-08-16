from datetime import timedelta
from decimal import Decimal

from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from orders.models import ShippingZone
from orders.models import Order
from products.models import Category, Product

from .models import ContentPage, Offer


class SeedCatalogDemoTests(TestCase):
    def test_command_creates_catalog_and_is_idempotent(self):
        call_command("seed_catalog_demo", no_images=True, verbosity=0)

        self.assertEqual(Category.objects.count(), 6)
        self.assertEqual(Product.objects.filter(sku__startswith="LUM-").count(), 10)
        self.assertEqual(Offer.objects.count(), 3)
        self.assertTrue(all(offer.products.exists() for offer in Offer.objects.all()))

        call_command("seed_catalog_demo", no_images=True, verbosity=0)

        self.assertEqual(Category.objects.count(), 6)
        self.assertEqual(Product.objects.filter(sku__startswith="LUM-").count(), 10)
        self.assertEqual(Offer.objects.count(), 3)


class PublicPageSmokeTests(TestCase):
    def setUp(self):
        category = Category.objects.create(name="العناية")
        self.product = Product.objects.create(
            name="منتج تجريبي", sku="DEMO-1", category=category,
            description="وصف تجريبي", price=Decimal("100"), stock_quantity=5,
            is_best_seller=True, is_new=True,
        )
        ShippingZone.objects.create(name="القاهرة", shipping_cost=Decimal("60"))
        ContentPage.objects.create(slug="من-نحن", title="من نحن", content="محتوى")

    def test_public_pages_render(self):
        urls = [
            reverse("core:home"), reverse("products:list"),
            self.product.get_absolute_url(), reverse("core:search") + "?q=منتج",
            reverse("core:contact"), reverse("core:page", args=["من-نحن"]),
            reverse("cart:detail"), reverse("accounts:login"), reverse("accounts:register"),
        ]
        for url in urls:
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 200)

    def test_checkout_page_renders_with_session_cart(self):
        self.client.post(reverse("cart:add", args=[self.product.pk]), {"quantity": 1})
        response = self.client.get(reverse("orders:checkout"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "إتمام الطلب")

    def test_guest_can_complete_cash_on_delivery_checkout(self):
        self.client.post(reverse("cart:add", args=[self.product.pk]), {"quantity": 1})
        self.client.get(reverse("orders:checkout"))
        data = {
            "full_name": "عميلة المتجر", "phone": "01012345678", "alternative_phone": "",
            "governorate": ShippingZone.objects.get().pk, "city": "مدينة نصر",
            "address": "10 شارع الاختبار", "landmark": "", "notes": "",
            "payment_method": Order.PaymentMethod.CASH,
            "terms_accepted": "on",
            "idempotency_key": self.client.session["checkout_idempotency_key"],
        }
        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(reverse("orders:checkout"), data)
        self.assertEqual(response.status_code, 302)
        self.assertIn("/checkout/success/", response.url)
        order = Order.objects.get()
        self.assertEqual(order.payment_status, Order.PaymentStatus.UNPAID)
        self.assertEqual(self.client.get(response.url).status_code, 200)

    def test_active_offer_is_shown_and_links_to_its_products(self):
        self.product.old_price = Decimal("125.00")
        self.product.save(update_fields=["old_price", "updated_at"])
        offer = Offer.objects.create(title="عرض نهاية الأسبوع", subtitle="لفترة محدودة")
        offer.products.add(self.product)

        home_response = self.client.get(reverse("core:home"))
        self.assertContains(home_response, "عرض نهاية الأسبوع")
        self.assertContains(home_response, f"?offer={offer.pk}")

        products_response = self.client.get(reverse("products:list"), {"offer": offer.pk})
        self.assertContains(products_response, "عرض نهاية الأسبوع")
        self.assertContains(products_response, self.product.name)

    def test_scheduled_or_disabled_offer_is_hidden(self):
        future_offer = Offer.objects.create(
            title="عرض قادم", starts_at=timezone.now() + timedelta(days=1)
        )
        future_offer.products.add(self.product)
        disabled_offer = Offer.objects.create(title="عرض متوقف", is_active=False)
        disabled_offer.products.add(self.product)

        response = self.client.get(reverse("core:home"))
        self.assertNotContains(response, future_offer.title)
        self.assertNotContains(response, disabled_offer.title)

    def test_invalid_price_filters_do_not_crash(self):
        for parameter in ["min_price", "max_price"]:
            with self.subTest(parameter=parameter):
                response = self.client.get(reverse("products:list"), {parameter: "abc"})
                self.assertEqual(response.status_code, 200)
                self.assertTrue(response.context["filter_form"].errors)
