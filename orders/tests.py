from datetime import timedelta
from decimal import Decimal
from io import BytesIO
from types import SimpleNamespace
import tempfile

from django.contrib.sessions.backends.db import SessionStore
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.utils import timezone
from PIL import Image

from cart.cart import Cart
from core.models import StoreSettings
from core.validators import validate_image_upload
from products.models import Category, Product

from .forms import CheckoutForm
from .models import Coupon, Order, ShippingZone
from .services import calculate_shipping, create_order, update_order_status


def image_upload(name="receipt.jpg"):
    output = BytesIO()
    Image.new("RGB", (20, 20), "white").save(output, "JPEG")
    return SimpleUploadedFile(name, output.getvalue(), content_type="image/jpeg")


class CouponAndShippingTests(TestCase):
    def setUp(self):
        self.zone = ShippingZone.objects.create(name="القاهرة", shipping_cost=Decimal("60"))

    def test_percentage_coupon_respects_minimum(self):
        now = timezone.now()
        coupon = Coupon.objects.create(
            code="SAVE10", discount_type=Coupon.DiscountType.PERCENTAGE,
            value=10, minimum_order=200, start_date=now - timedelta(days=1),
            end_date=now + timedelta(days=1), is_active=True,
        )
        self.assertEqual(coupon.calculate_discount(Decimal("300")), Decimal("30.00"))
        self.assertEqual(coupon.calculate_discount(Decimal("100")), Decimal("0.00"))

    def test_free_shipping_threshold(self):
        settings = StoreSettings.load()
        settings.free_shipping_threshold = Decimal("500")
        settings.save()
        self.assertEqual(calculate_shipping(Decimal("500"), self.zone), Decimal("0.00"))
        self.assertEqual(calculate_shipping(Decimal("499"), self.zone), Decimal("60"))


class CheckoutTests(TestCase):
    @classmethod
    def setUpClass(cls):
        cls._media_dir = tempfile.TemporaryDirectory()
        cls._media_override = override_settings(MEDIA_ROOT=cls._media_dir.name)
        cls._media_override.enable()
        super().setUpClass()

    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        cls._media_override.disable()
        cls._media_dir.cleanup()

    def setUp(self):
        self.category = Category.objects.create(name="البشرة")
        self.product = Product.objects.create(
            name="سيروم", sku="SRM-1", category=self.category,
            description="وصف", price=Decimal("200"), stock_quantity=4,
        )
        self.zone = ShippingZone.objects.create(name="الجيزة", shipping_cost=Decimal("50"))
        session = SessionStore()
        session.create()
        self.cart = Cart(SimpleNamespace(session=session))
        self.cart.add(self.product, 2)
        self.base_data = {
            "full_name": "عميلة تجريبية", "phone": "01012345678",
            "alternative_phone": "", "governorate": self.zone.pk,
            "city": "الدقي", "address": "شارع تجريبي 10",
            "landmark": "بجوار المتجر", "notes": "",
            "payment_method": Order.PaymentMethod.CASH,
        }

    def test_order_creation_snapshots_price_and_reduces_stock(self):
        form = CheckoutForm(data=self.base_data)
        self.assertTrue(form.is_valid(), form.errors)
        order = create_order(form=form, cart=self.cart)
        self.product.refresh_from_db()
        item = order.items.get()
        self.assertEqual(order.total, Decimal("450.00"))
        self.assertEqual(item.product_name, "سيروم")
        self.assertEqual(item.unit_price, Decimal("200"))
        self.assertEqual(self.product.stock_quantity, 2)

    def test_instapay_receipt_is_required(self):
        data = {**self.base_data, "payment_method": Order.PaymentMethod.INSTAPAY}
        form = CheckoutForm(data=data)
        self.assertFalse(form.is_valid())
        self.assertIn("payment_receipt", form.errors)

    def test_instapay_receipt_accepts_valid_image(self):
        data = {**self.base_data, "payment_method": Order.PaymentMethod.INSTAPAY}
        form = CheckoutForm(data=data, files={"payment_receipt": image_upload()})
        self.assertTrue(form.is_valid(), form.errors)

    def test_instapay_order_starts_pending_verification(self):
        data = {**self.base_data, "payment_method": Order.PaymentMethod.INSTAPAY}
        form = CheckoutForm(data=data, files={"payment_receipt": image_upload()})
        self.assertTrue(form.is_valid(), form.errors)
        order = create_order(form=form, cart=self.cart)
        self.assertEqual(order.payment_status, Order.PaymentStatus.PENDING)
        self.assertTrue(order.payment_receipt.name)

    def test_cancelling_order_restores_stock_once(self):
        form = CheckoutForm(data=self.base_data)
        self.assertTrue(form.is_valid(), form.errors)
        order = create_order(form=form, cart=self.cart)
        update_order_status(order, Order.Status.CANCELLED)
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock_quantity, 4)
        order.refresh_from_db()
        update_order_status(order, Order.Status.CANCELLED)
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock_quantity, 4)

    def test_upload_validation_rejects_fake_image(self):
        fake = SimpleUploadedFile("receipt.jpg", b"not-an-image", content_type="image/jpeg")
        with self.assertRaises(ValidationError):
            validate_image_upload(fake)

    def test_upload_validation_rejects_oversized_file(self):
        oversized = SimpleUploadedFile("receipt.jpg", b"x" * (5 * 1024 * 1024 + 1), content_type="image/jpeg")
        with self.assertRaises(ValidationError):
            validate_image_upload(oversized)
