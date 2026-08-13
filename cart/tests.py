from decimal import Decimal
from types import SimpleNamespace

from django.contrib.sessions.backends.db import SessionStore
from django.test import TestCase

from products.models import Category, Product

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
