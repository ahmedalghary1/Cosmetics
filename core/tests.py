from decimal import Decimal

from django.test import TestCase
from django.urls import reverse

from orders.models import ShippingZone
from orders.models import Order
from products.models import Category, Product

from .models import ContentPage


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
        data = {
            "full_name": "عميلة المتجر", "phone": "01012345678", "alternative_phone": "",
            "governorate": ShippingZone.objects.get().pk, "city": "مدينة نصر",
            "address": "10 شارع الاختبار", "landmark": "", "notes": "",
            "payment_method": Order.PaymentMethod.CASH,
        }
        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(reverse("orders:checkout"), data)
        self.assertEqual(response.status_code, 302)
        self.assertIn("/checkout/success/", response.url)
        order = Order.objects.get()
        self.assertEqual(order.payment_status, Order.PaymentStatus.UNPAID)
        self.assertEqual(self.client.get(response.url).status_code, 200)
