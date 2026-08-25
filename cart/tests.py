from decimal import Decimal
from types import SimpleNamespace

from django.contrib.sessions.backends.db import SessionStore
from django.test import TestCase
from django.urls import reverse

from products.models import BundleItem, Category, Product, ProductVariant

from .cart import Cart


class CartTests(TestCase):
    def setUp(self):
        category = Category.objects.create(name="الجسم")
        self.product = Product.objects.create(
            name="لوشن", sku="LOT-1", category=category,
            description="وصف", price=Decimal("125.50"), stock_quantity=4,
        )
        self.session = SessionStore()
        self.session.create()
        self.cart = Cart(SimpleNamespace(session=self.session))

    def test_cart_calculates_quantity_and_subtotal(self):
        self.cart.add(self.product, 2)
        self.assertEqual(len(self.cart), 2)
        self.assertEqual(self.cart.subtotal, Decimal("251.00"))

    def test_cart_rejects_quantity_above_stock(self):
        with self.assertRaisesMessage(ValueError, "الكمية المطلوبة أكبر"):
            self.cart.add(self.product, 5)

    def test_external_next_redirect_is_blocked(self):
        response = self.client.post(
            reverse("cart:add", args=[self.product.pk]),
            {"quantity": 1, "next": "https://evil.example/phishing"},
        )
        self.assertEqual(response.status_code, 302)
        self.assertNotEqual(response.url, "https://evil.example/phishing")

    def test_reserved_stock_is_not_available_to_cart(self):
        self.product.reserved_quantity = 3
        self.product.save(update_fields=["reserved_quantity", "updated_at"])
        with self.assertRaises(ValueError):
            self.cart.add(self.product, 2)

    def test_variant_product_requires_variant_and_uses_variant_price(self):
        self.product.has_variants = True
        self.product.save(update_fields=["has_variants", "updated_at"])
        variant = ProductVariant.objects.create(
            product=self.product, sku="LOT-1-50", option_summary="50 ml",
            price=Decimal("150"), stock_quantity=2,
        )
        with self.assertRaises(ValueError):
            self.cart.add(self.product, 1)
        self.cart.add(self.product, 2, variant=variant)
        item = list(self.cart)[0]
        self.assertEqual(item["variant"], variant)
        self.assertEqual(item["total_price"], Decimal("300"))

    def test_inactive_category_product_is_purged_from_existing_cart(self):
        self.cart.add(self.product, 1)
        self.product.category.is_active = False
        self.product.category.save(update_fields=["is_active", "updated_at"])
        self.assertEqual(list(self.cart), [])
        self.assertEqual(len(self.cart), 0)

    def test_bundle_is_added_once_and_respects_component_stock(self):
        bundle = Product.objects.create(
            name="بوكس الجسم", sku="BODY-BOX", category=self.product.category,
            description="وصف", price=Decimal("200"), is_bundle=True,
        )
        BundleItem.objects.create(bundle=bundle, product=self.product, quantity=2)

        self.cart.add(bundle, 2)
        item = list(self.cart)[0]

        self.assertEqual(item["product"], bundle)
        self.assertEqual(item["quantity"], 2)
        self.assertEqual(item["total_price"], Decimal("400"))
        with self.assertRaises(ValueError):
            self.cart.add(bundle, 1)
