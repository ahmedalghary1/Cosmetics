from decimal import Decimal

from django.test import TestCase

from .models import Category, Product


class ProductModelTests(TestCase):
    def setUp(self):
        self.category = Category.objects.create(name="العناية بالبشرة")

    def test_arabic_slug_and_discount_are_generated(self):
        product = Product.objects.create(
            name="سيروم الإشراقة",
            sku="SER-1",
            category=self.category,
            description="وصف",
            price=Decimal("80.00"),
            old_price=Decimal("100.00"),
            stock_quantity=3,
        )
        self.assertIn("سيروم", product.slug)
        self.assertEqual(product.discount_percentage, 20)
        self.assertTrue(product.in_stock)

    def test_out_of_stock_product_is_not_available(self):
        product = Product.objects.create(
            name="كريم", sku="CRM-1", category=self.category,
            description="وصف", price=Decimal("50.00"), stock_quantity=0,
        )
        self.assertFalse(product.in_stock)
