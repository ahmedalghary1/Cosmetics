from decimal import Decimal

from django.core import mail
from django.test import TestCase, override_settings
from django.core.exceptions import ValidationError
from django.urls import reverse

from core.models import StoreSettings

from .models import BackInStockSubscription, BundleItem, Category, InventoryBatch, Product, ProductVariant
from .services import notify_back_in_stock


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

    def test_product_can_appear_in_multiple_categories(self):
        second_category = Category.objects.create(name="الأكثر مبيعًا")
        product = Product.objects.create(
            name="كريم متعدد الأقسام", sku="MULTI-CATEGORY", category=self.category,
            description="وصف", price=Decimal("75.00"), stock_quantity=2,
        )
        product.categories.add(second_category)

        self.assertCountEqual(
            product.categories.values_list("pk", flat=True),
            [self.category.pk, second_category.pk],
        )
        response = self.client.get(
            reverse("product_categories:detail", args=[second_category.slug]),
        )
        self.assertContains(response, product.name)

    def test_bundle_stock_is_limited_by_its_components(self):
        first = Product.objects.create(
            name="غسول", sku="BND-C1", category=self.category,
            description="وصف", price=Decimal("50"), stock_quantity=5,
        )
        second = Product.objects.create(
            name="كريم", sku="BND-C2", category=self.category,
            description="وصف", price=Decimal("60"), stock_quantity=7,
        )
        bundle = Product.objects.create(
            name="بوكس العناية", sku="BND-1", category=self.category,
            description="وصف", price=Decimal("90"), is_bundle=True,
        )
        BundleItem.objects.create(bundle=bundle, product=first, quantity=2)
        BundleItem.objects.create(bundle=bundle, product=second, quantity=1)

        self.assertEqual(bundle.available_stock, 2)
        self.assertTrue(bundle.in_stock)

    def test_negative_price_is_rejected(self):
        product = Product(
            name="منتج بسعر خاطئ", sku="NEG-PRICE", category=self.category,
            description="وصف", price=Decimal("-1.00"), stock_quantity=1,
        )
        with self.assertRaises(ValidationError):
            product.full_clean()

    def test_negative_stock_is_rejected(self):
        product = Product(
            name="منتج بمخزون خاطئ", sku="NEG-STOCK", category=self.category,
            description="وصف", price=Decimal("10.00"), stock_quantity=-1,
        )
        with self.assertRaises(ValidationError):
            product.full_clean()

    def test_reserved_quantity_cannot_exceed_stock(self):
        product = Product(
            name="منتج محجوز", sku="RESERVED", category=self.category,
            description="وصف", price=Decimal("10"), stock_quantity=2, reserved_quantity=3,
        )
        with self.assertRaises(ValidationError):
            product.full_clean()

    def test_variant_uses_parent_price_and_independent_available_stock(self):
        product = Product.objects.create(
            name="عطر", sku="PERFUME", category=self.category, description="وصف",
            price=Decimal("300"), stock_quantity=0, has_variants=True,
        )
        variant = ProductVariant.objects.create(
            product=product, sku="PERFUME-50", option_summary="50 ml",
            stock_quantity=4, reserved_quantity=1,
        )
        self.assertEqual(variant.effective_price, Decimal("300"))
        self.assertEqual(variant.available_stock, 3)
        self.assertEqual(product.available_stock, 3)

    def test_batch_variant_must_belong_to_same_product(self):
        first = Product.objects.create(
            name="الأول", sku="FIRST", category=self.category, description="x",
            price=Decimal("10"), has_variants=True,
        )
        second = Product.objects.create(
            name="الثاني", sku="SECOND", category=self.category, description="x", price=Decimal("10"),
        )
        variant = ProductVariant.objects.create(
            product=first, sku="FIRST-S", option_summary="صغير", stock_quantity=1,
        )
        batch = InventoryBatch(product=second, variant=variant, batch_number="BAD", quantity=1)
        with self.assertRaises(ValidationError):
            batch.full_clean()

    @override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend")
    def test_back_in_stock_subscription_is_sent_once(self):
        product = Product.objects.create(
            name="منتج منتظر", sku="WAITING", category=self.category,
            description="وصف", price=Decimal("125"), stock_quantity=0,
        )
        response = self.client.post(
            reverse("products:back_in_stock", args=[product.pk]),
            {"email": "Customer@Example.com"},
        )
        self.assertRedirects(response, product.get_absolute_url())
        subscription = BackInStockSubscription.objects.get()
        self.assertEqual(subscription.email, "customer@example.com")

        product.stock_quantity = 3
        product.save(update_fields=["stock_quantity", "updated_at"])
        self.assertEqual(notify_back_in_stock(product.pk), 1)
        subscription.refresh_from_db()
        self.assertFalse(subscription.is_active)
        self.assertIsNotNone(subscription.notified_at)
        self.assertEqual(len(mail.outbox), 1)
        self.assertIn(product.name, mail.outbox[0].subject)
        self.assertEqual(notify_back_in_stock(product.pk), 0)
        self.assertEqual(len(mail.outbox), 1)

    def test_product_page_includes_configured_analytics(self):
        product = Product.objects.create(
            name="منتج تحليلات", sku="ANALYTICS", category=self.category,
            description="وصف", price=Decimal("90"), stock_quantity=1,
        )
        store = StoreSettings.load()
        store.google_analytics_id = "G-ABC123"
        store.meta_pixel_id = "123456789"
        store.tiktok_pixel_id = "C123ABC"
        store.full_clean()
        store.save()

        response = self.client.get(product.get_absolute_url())
        self.assertContains(response, "www.googletagmanager.com/gtag/js")
        self.assertContains(response, "connect.facebook.net/en_US/fbevents.js")
        self.assertContains(response, "analytics.tiktok.com/i18n/pixel/events.js")
        self.assertContains(response, "product-analytics-data")
