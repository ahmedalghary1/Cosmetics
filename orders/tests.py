from datetime import date, timedelta
from decimal import Decimal
from io import BytesIO
from types import SimpleNamespace
import uuid
from unittest.mock import patch

from django.contrib.sessions.backends.db import SessionStore
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from PIL import Image

from cart.cart import Cart
from core.models import StoreSettings
from core.validators import validate_image_upload
from products.models import Category, InventoryBatch, Product

from .forms import CheckoutForm
from .models import (
    Coupon, CouponRedemption, InventoryReservation, Order, ReturnRequest,
    ReturnRequestItem, ShippingZone,
)
from .services import (
    CheckoutError,
    OrderTransitionError,
    calculate_shipping,
    create_order,
    release_expired_reservations,
    process_return,
    transition_order,
    update_order_status,
)


def image_upload(name="receipt.jpg"):
    output = BytesIO()
    Image.new("RGB", (20, 20), "white").save(output, "JPEG")
    return SimpleUploadedFile(name, output.getvalue(), content_type="image/jpeg")


def session_cart(product, quantity=1):
    session = SessionStore()
    session.create()
    cart = Cart(SimpleNamespace(session=session, user=None))
    cart.add(product, quantity)
    return cart


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

    def test_invalid_shipping_zone_returns_validation_error(self):
        response = self.client.get(reverse("orders:shipping_quote"), {"zone": "abc"})
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["message"], "يرجى اختيار محافظة صحيحة.")


class CheckoutTests(TestCase):
    def setUp(self):
        self.category = Category.objects.create(name="البشرة")
        self.product = Product.objects.create(
            name="سيروم", sku="SRM-1", category=self.category,
            description="وصف", price=Decimal("200"), stock_quantity=4,
        )
        self.zone = ShippingZone.objects.create(name="الجيزة", shipping_cost=Decimal("50"))
        settings = StoreSettings.load()
        settings.instapay_enabled = True
        settings.instapay_account_name = "Store"
        settings.instapay_address = "store@instapay"
        settings.inventory_reservation_minutes = 30
        settings.save()
        self.cart = session_cart(self.product, 2)
        self.base_data = {
            "full_name": "عميلة تجريبية", "email": "", "phone": "01012345678",
            "alternative_phone": "", "governorate": self.zone.pk,
            "city": "الدقي", "address": "شارع تجريبي 10",
            "landmark": "بجوار المتجر", "notes": "",
            "payment_method": Order.PaymentMethod.CASH, "terms_accepted": "on",
        }

    def form(self, data=None, files=None):
        return CheckoutForm(
            data=data or self.base_data,
            files=files,
            store_settings=StoreSettings.load(),
        )

    def create(self, **kwargs):
        form = self.form()
        self.assertTrue(form.is_valid(), form.errors)
        return create_order(form=form, cart=self.cart, **kwargs)

    def test_order_creation_snapshots_price_and_reserves_stock(self):
        order = self.create()
        self.product.refresh_from_db()
        item = order.items.get()
        self.assertEqual(order.total, Decimal("450.00"))
        self.assertEqual(item.product_name, "سيروم")
        self.assertEqual(item.unit_price, Decimal("200"))
        self.assertEqual(self.product.stock_quantity, 4)
        self.assertEqual(self.product.reserved_quantity, 2)
        self.assertEqual(order.reservations.get().status, InventoryReservation.Status.ACTIVE)
        self.assertTrue(order.audit_logs.filter(action="order_created").exists())

    def test_confirmation_consumes_reservation_and_delivery_counts_sales(self):
        order = self.create()
        order = update_order_status(order, Order.Status.CONFIRMED)
        self.product.refresh_from_db()
        self.assertEqual((self.product.stock_quantity, self.product.reserved_quantity), (2, 0))
        self.assertEqual(self.product.sales_count, 0)
        order = update_order_status(order, Order.Status.PREPARING)
        order = update_order_status(order, Order.Status.SHIPPED)
        update_order_status(order, Order.Status.DELIVERED)
        self.product.refresh_from_db()
        self.assertEqual(self.product.sales_count, 2)

    def test_cancelling_new_order_releases_reservation_once(self):
        order = self.create()
        update_order_status(order, Order.Status.CANCELLED)
        self.product.refresh_from_db()
        self.assertEqual((self.product.stock_quantity, self.product.reserved_quantity), (4, 0))
        order.refresh_from_db()
        update_order_status(order, Order.Status.CANCELLED)
        self.product.refresh_from_db()
        self.assertEqual((self.product.stock_quantity, self.product.reserved_quantity), (4, 0))

    def test_cancelling_confirmed_order_restocks_once(self):
        order = self.create()
        order = update_order_status(order, Order.Status.CONFIRMED)
        update_order_status(order, Order.Status.CANCELLED)
        self.product.refresh_from_db()
        self.assertEqual((self.product.stock_quantity, self.product.reserved_quantity), (4, 0))

    def test_idempotency_key_returns_same_order(self):
        key = uuid.uuid4()
        first = self.create(idempotency_key=key)
        second = create_order(form=self.form(), cart=self.cart, idempotency_key=key)
        self.assertEqual(first.pk, second.pk)
        self.assertEqual(Order.objects.count(), 1)
        self.assertEqual(InventoryReservation.objects.count(), 1)

    def test_conditional_update_prevents_overselling(self):
        second_cart = session_cart(self.product, 3)
        self.create()
        second_form = self.form()
        self.assertTrue(second_form.is_valid(), second_form.errors)
        with self.assertRaises(CheckoutError):
            create_order(form=second_form, cart=second_cart)
        self.product.refresh_from_db()
        self.assertEqual(self.product.reserved_quantity, 2)

    def test_instapay_is_hidden_when_store_configuration_is_incomplete(self):
        settings = StoreSettings.load()
        settings.instapay_enabled = False
        settings.save()
        data = {**self.base_data, "payment_method": Order.PaymentMethod.INSTAPAY}
        form = CheckoutForm(data=data, store_settings=settings)
        self.assertFalse(form.is_valid())
        self.assertIn("payment_method", form.errors)

    def test_instapay_receipt_is_required(self):
        data = {**self.base_data, "payment_method": Order.PaymentMethod.INSTAPAY}
        form = self.form(data=data)
        self.assertFalse(form.is_valid())
        self.assertIn("payment_receipt", form.errors)

    def test_instapay_order_requires_verified_payment_before_confirmation(self):
        data = {**self.base_data, "payment_method": Order.PaymentMethod.INSTAPAY}
        form = self.form(data=data, files={"payment_receipt": image_upload()})
        self.assertTrue(form.is_valid(), form.errors)
        order = create_order(form=form, cart=self.cart)
        self.assertEqual(order.status, Order.Status.AWAITING_PAYMENT)
        with self.assertRaises(OrderTransitionError):
            transition_order(order, new_status=Order.Status.CONFIRMED)
        order = transition_order(
            order,
            new_status=Order.Status.CONFIRMED,
            payment_status=Order.PaymentStatus.VERIFIED,
        )
        self.assertEqual(order.payment_status, Order.PaymentStatus.VERIFIED)
        order.payment_receipt.delete(save=False)

    def test_fefo_batch_allocation_and_cost_snapshot(self):
        self.product.stock_quantity = 10
        self.product.save(update_fields=["stock_quantity", "updated_at"])
        early = InventoryBatch.objects.create(
            product=self.product, batch_number="EARLY", quantity=5,
            expiry_date=date.today() + timedelta(days=10), purchase_cost=Decimal("80"),
        )
        late = InventoryBatch.objects.create(
            product=self.product, batch_number="LATE", quantity=5,
            expiry_date=date.today() + timedelta(days=50), purchase_cost=Decimal("100"),
        )
        cart = session_cart(self.product, 6)
        form = self.form()
        self.assertTrue(form.is_valid(), form.errors)
        order = create_order(form=form, cart=cart)
        allocations = order.reservations.get().batch_allocations.order_by("batch__expiry_date")
        self.assertEqual([(a.batch_id, a.quantity) for a in allocations], [(early.pk, 5), (late.pk, 1)])
        self.assertEqual(order.items.get().unit_cost, Decimal("83.33"))

    def test_expired_batches_cannot_be_sold(self):
        InventoryBatch.objects.create(
            product=self.product, batch_number="EXPIRED", quantity=4,
            expiry_date=date.today() - timedelta(days=1), purchase_cost=Decimal("50"),
        )
        with self.assertRaises(CheckoutError):
            self.create()
        self.product.refresh_from_db()
        self.assertEqual(self.product.reserved_quantity, 0)

    def test_expired_reservation_is_released(self):
        order = self.create()
        order.reservations.update(reserved_until=timezone.now() - timedelta(minutes=1))
        self.assertEqual(release_expired_reservations(), 1)
        self.product.refresh_from_db()
        order.refresh_from_db()
        self.assertEqual(self.product.reserved_quantity, 0)
        self.assertEqual(order.status, Order.Status.CANCELLED)

    def test_coupon_is_reserved_then_consumed_and_released(self):
        now = timezone.now()
        coupon = Coupon.objects.create(
            code="ONLY1", discount_type=Coupon.DiscountType.FIXED, value=Decimal("20"),
            start_date=now - timedelta(days=1), end_date=now + timedelta(days=1), usage_limit=1,
        )
        self.cart.session[Cart.COUPON_KEY] = coupon.code
        order = self.create()
        coupon.refresh_from_db()
        self.assertEqual(coupon.used_count, 0)
        self.assertEqual(order.coupon_redemption.status, CouponRedemption.Status.RESERVED)
        order = update_order_status(order, Order.Status.CONFIRMED)
        coupon.refresh_from_db()
        self.assertEqual(coupon.used_count, 1)
        update_order_status(order, Order.Status.CANCELLED)
        coupon.refresh_from_db()
        self.assertEqual(coupon.used_count, 0)

    def test_upload_validation_rejects_fake_and_oversized_images(self):
        fake = SimpleUploadedFile("receipt.jpg", b"not-an-image", content_type="image/jpeg")
        with self.assertRaises(ValidationError):
            validate_image_upload(fake)
        oversized = SimpleUploadedFile("receipt.jpg", b"x" * (5 * 1024 * 1024 + 1), content_type="image/jpeg")
        with self.assertRaises(ValidationError):
            validate_image_upload(oversized)

    def test_notification_failure_does_not_roll_back_order(self):
        data = {**self.base_data, "email": "customer@example.com"}
        form = self.form(data=data)
        self.assertTrue(form.is_valid(), form.errors)
        with self.assertLogs("orders.services", level="ERROR"):
            with patch("orders.services.send_mail", side_effect=RuntimeError("mail unavailable")):
                with self.captureOnCommitCallbacks(execute=True):
                    order = create_order(form=form, cart=self.cart)
        self.assertTrue(Order.objects.filter(pk=order.pk).exists())

    def test_return_only_restocks_marked_items_and_records_refund(self):
        user = get_user_model().objects.create_user(username="return-user", password="safe-password-123")
        order = self.create(user=user)
        order = update_order_status(order, Order.Status.CONFIRMED)
        order = update_order_status(order, Order.Status.PREPARING)
        order = update_order_status(order, Order.Status.SHIPPED)
        order = update_order_status(order, Order.Status.DELIVERED)
        return_request = ReturnRequest.objects.create(order=order, user=user, reason="عبوة غير مفتوحة")
        return_item = ReturnRequestItem.objects.create(
            return_request=return_request, order_item=order.items.get(), quantity=1,
        )
        return_request = process_return(
            return_request, new_status=ReturnRequest.Status.APPROVED,
            refund_amount=Decimal("0"), admin_note="مقبول", restockable={return_item.pk: True},
        )
        return_request = process_return(
            return_request, new_status=ReturnRequest.Status.RECEIVED,
            refund_amount=Decimal("0"), admin_note="تم الاستلام", restockable={return_item.pk: True},
        )
        self.product.refresh_from_db()
        self.assertEqual(self.product.stock_quantity, 3)
        process_return(
            return_request, new_status=ReturnRequest.Status.REFUNDED,
            refund_amount=Decimal("200"), admin_note="تم الرد", restockable={return_item.pk: True},
        )
        order.refresh_from_db()
        self.product.refresh_from_db()
        self.assertEqual(order.refunded_amount, Decimal("200"))
        self.assertEqual(self.product.sales_count, 1)
