from datetime import date, timedelta
from decimal import Decimal
import logging
import secrets

from django.core.mail import send_mail
from django.db import IntegrityError, OperationalError, transaction
from django.db.models import F, Q, Value
from django.db.models.functions import Greatest
from django.utils import timezone

from core.models import StoreSettings
from products.models import InventoryBatch, Product, ProductVariant

from .models import (
    Coupon,
    CouponRedemption,
    InventoryReservation,
    Order,
    OrderAuditLog,
    OrderItem,
    ReservationBatchAllocation,
    ReturnRequest,
)


logger = logging.getLogger(__name__)


class CheckoutError(Exception):
    pass


class OrderTransitionError(ValueError):
    pass


def calculate_shipping(subtotal_after_discount, zone):
    threshold = StoreSettings.load().free_shipping_threshold
    if threshold is not None and subtotal_after_discount >= threshold:
        return Decimal("0.00")
    return zone.shipping_cost


def build_order_number():
    return f"ORD-{date.today():%y%m%d}-{secrets.token_hex(3).upper()}"


def customer_coupon_key(*, user, phone):
    if user and user.is_authenticated:
        return f"user:{user.pk}"
    normalized_phone = "".join(character for character in phone if character.isdigit())
    return f"phone:{normalized_phone}"


def coupon_eligible_subtotal(coupon, cart_items):
    product_ids = set(coupon.products.values_list("id", flat=True))
    category_ids = set(coupon.categories.values_list("id", flat=True))
    unrestricted = not product_ids and not category_ids
    return sum(
        (
            item["total_price"]
            for item in cart_items
            if unrestricted
            or item["product"].pk in product_ids
            or item["product"].category_id in category_ids
        ),
        Decimal("0.00"),
    )


def validate_coupon(coupon, *, cart_items, user, phone):
    if not coupon:
        return None, Decimal("0.00")
    eligible_subtotal = coupon_eligible_subtotal(coupon, cart_items)
    if not coupon.is_valid_for(eligible_subtotal):
        return None, Decimal("0.00")
    active_statuses = [CouponRedemption.Status.RESERVED, CouponRedemption.Status.CONSUMED]
    if coupon.usage_limit is not None:
        reserved_count = coupon.redemptions.filter(status__in=active_statuses).count()
        if reserved_count >= coupon.usage_limit:
            return None, Decimal("0.00")
    key = customer_coupon_key(user=user, phone=phone)
    if coupon.max_uses_per_customer is not None:
        customer_count = coupon.redemptions.filter(customer_key=key, status__in=active_statuses).count()
        if customer_count >= coupon.max_uses_per_customer:
            return None, Decimal("0.00")
    return coupon, coupon.calculate_discount(eligible_subtotal)


def _reserve_batches(reservation):
    """Allocate unexpired batches in FEFO order when the product uses batch tracking."""
    batch_scope = InventoryBatch.objects.filter(
        product=reservation.product,
        variant=reservation.variant,
        is_active=True,
    )
    if not batch_scope.exists():
        return Decimal("0.00")

    remaining = reservation.quantity
    total_cost = Decimal("0.00")
    eligible = batch_scope.filter(
        Q(expiry_date__isnull=True) | Q(expiry_date__gte=timezone.localdate())
    ).order_by(F("expiry_date").asc(nulls_last=True), "received_date", "id")
    for batch in eligible:
        if remaining <= 0:
            break
        available = max(batch.quantity - batch.reserved_quantity, 0)
        allocation_quantity = min(available, remaining)
        if allocation_quantity <= 0:
            continue
        updated = InventoryBatch.objects.filter(
            pk=batch.pk,
            quantity__gte=F("reserved_quantity") + allocation_quantity,
        ).update(reserved_quantity=F("reserved_quantity") + allocation_quantity)
        if not updated:
            raise CheckoutError("تغير المخزون أثناء الطلب. يرجى المحاولة مرة أخرى.")
        ReservationBatchAllocation.objects.create(
            reservation=reservation, batch=batch, quantity=allocation_quantity,
        )
        total_cost += batch.purchase_cost * allocation_quantity
        remaining -= allocation_quantity
    if remaining:
        raise CheckoutError(f"لا توجد تشغيلات صالحة كافية للمنتج «{reservation.product.name}».")
    return (total_cost / reservation.quantity).quantize(Decimal("0.01"))


def _reserve_inventory(*, order, product, variant, quantity, reserved_until):
    if variant:
        updated = ProductVariant.objects.filter(
            pk=variant.pk,
            is_active=True,
            product=product,
            product__is_active=True,
            product__category__is_active=True,
            stock_quantity__gte=F("reserved_quantity") + quantity,
        ).update(reserved_quantity=F("reserved_quantity") + quantity)
        available = variant.available_stock
    else:
        updated = Product.objects.filter(
            pk=product.pk,
            is_active=True,
            category__is_active=True,
            has_variants=False,
            stock_quantity__gte=F("reserved_quantity") + quantity,
        ).update(reserved_quantity=F("reserved_quantity") + quantity)
        available = product.available_stock
    if not updated:
        raise CheckoutError(f"المتوفر من «{product.name}» هو {available} فقط.")
    reservation = InventoryReservation.objects.create(
        order=order,
        product=product,
        variant=variant,
        quantity=quantity,
        reserved_until=reserved_until,
    )
    return reservation, _reserve_batches(reservation)


def _create_order(*, form, cart, user, idempotency_key):
    existing = Order.objects.filter(idempotency_key=idempotency_key).first()
    if existing:
        return existing

    cart_items = list(cart)
    if not cart_items:
        raise CheckoutError("سلة التسوق فارغة.")

    current_items = []
    subtotal = Decimal("0.00")
    for item in cart_items:
        product = Product.objects.active().filter(pk=item["product"].pk).first()
        if not product:
            raise CheckoutError("أحد المنتجات لم يعد متاحًا. حدّث السلة وحاول مرة أخرى.")
        variant = None
        if item.get("variant"):
            variant = ProductVariant.objects.filter(
                pk=item["variant"].pk, product=product, is_active=True,
            ).first()
            if not variant:
                raise CheckoutError(f"الخيار المحدد للمنتج «{product.name}» لم يعد متاحًا.")
        elif product.has_variants:
            raise CheckoutError(f"يرجى اختيار نوع المنتج «{product.name}».")
        price = variant.effective_price if variant else product.price
        subtotal += price * item["quantity"]
        current_items.append({**item, "product": product, "variant": variant, "price": price})

    coupon = cart.coupon
    if coupon:
        coupon = Coupon.objects.get(pk=coupon.pk)
    coupon, discount = validate_coupon(
        coupon,
        cart_items=current_items,
        user=user,
        phone=form.cleaned_data["phone"],
    )
    store_settings = StoreSettings.load()
    shipping = calculate_shipping(subtotal - discount, form.cleaned_data["governorate"])
    payment_method = form.cleaned_data["payment_method"]
    payment_status = (
        Order.PaymentStatus.PENDING
        if payment_method == Order.PaymentMethod.INSTAPAY
        else Order.PaymentStatus.UNPAID
    )
    status = (
        Order.Status.AWAITING_PAYMENT
        if payment_method == Order.PaymentMethod.INSTAPAY
        else Order.Status.NEW
    )
    reserved_until = timezone.now() + timedelta(minutes=store_settings.inventory_reservation_minutes)

    order = form.save(commit=False)
    order.order_number = build_order_number()
    order.idempotency_key = idempotency_key
    order.user = user if user and user.is_authenticated else None
    order.subtotal = subtotal
    order.discount = discount
    order.shipping_cost = shipping
    order.total = subtotal - discount + shipping
    order.coupon = coupon
    order.payment_status = payment_status
    order.status = status
    order.reservation_expires_at = reserved_until
    order.terms_version = store_settings.terms_version
    order.terms_accepted_at = timezone.now()
    order.save()

    order_items = []
    for item in current_items:
        _, unit_cost = _reserve_inventory(
            order=order,
            product=item["product"],
            variant=item["variant"],
            quantity=item["quantity"],
            reserved_until=reserved_until,
        )
        order_items.append(OrderItem(
            order=order,
            product=item["product"],
            variant=item["variant"],
            product_name=item["product"].name,
            variant_name=item["variant"].option_summary if item["variant"] else "",
            sku=item["variant"].sku if item["variant"] else item["product"].sku,
            quantity=item["quantity"],
            unit_price=item["price"],
            total_price=item["price"] * item["quantity"],
            unit_cost=unit_cost,
            total_cost=unit_cost * item["quantity"],
        ))
    OrderItem.objects.bulk_create(order_items)

    if coupon:
        CouponRedemption.objects.create(
            coupon=coupon,
            order=order,
            user=order.user,
            customer_key=customer_coupon_key(user=user, phone=order.phone),
        )
    OrderAuditLog.objects.create(
        order=order,
        actor=order.user,
        action="order_created",
        new_values={
            "status": order.status,
            "payment_status": order.payment_status,
            "total": str(order.total),
        },
    )
    transaction.on_commit(cart.clear)
    transaction.on_commit(lambda: NotificationService.order_created(order.pk))
    return order


def create_order(*, form, cart, user=None, idempotency_key=None):
    idempotency_key = idempotency_key or secrets.token_hex(16)
    try:
        with transaction.atomic():
            return _create_order(
                form=form,
                cart=cart,
                user=user,
                idempotency_key=idempotency_key,
            )
    except CheckoutError:
        _delete_rolled_back_receipt(form)
        raise
    except (OperationalError, IntegrityError) as exc:
        _delete_rolled_back_receipt(form)
        logger.exception("Atomic checkout failed")
        if "locked" in str(exc).lower() or isinstance(exc, OperationalError):
            raise CheckoutError("المتجر مشغول لحظيًا. لم يتم إنشاء الطلب، يرجى المحاولة بعد لحظات.") from exc
        raise CheckoutError("تعذر إنشاء الطلب بأمان. يرجى المحاولة مرة أخرى.") from exc


def _delete_rolled_back_receipt(form):
    receipt = getattr(form.instance, "payment_receipt", None)
    if not receipt or not receipt.name:
        return
    if form.instance.pk and Order.objects.filter(pk=form.instance.pk).exists():
        return
    try:
        receipt.storage.delete(receipt.name)
    except Exception:
        logger.exception("Could not remove rolled-back payment receipt %s", receipt.name)


def _release_coupon(order):
    redemption = CouponRedemption.objects.filter(order=order).first()
    if not redemption or redemption.status == CouponRedemption.Status.RELEASED:
        return
    if redemption.status == CouponRedemption.Status.CONSUMED:
        Coupon.objects.filter(pk=redemption.coupon_id, used_count__gt=0).update(used_count=F("used_count") - 1)
    redemption.status = CouponRedemption.Status.RELEASED
    redemption.save(update_fields=["status", "updated_at"])
    order.coupon_consumed = False


def _consume_coupon(order):
    redemption = CouponRedemption.objects.filter(order=order).first()
    if not redemption or redemption.status != CouponRedemption.Status.RESERVED:
        return
    Coupon.objects.filter(pk=redemption.coupon_id).update(used_count=F("used_count") + 1)
    redemption.status = CouponRedemption.Status.CONSUMED
    redemption.save(update_fields=["status", "updated_at"])
    order.coupon_consumed = True


def _release_reservations(order, *, expired=False):
    reservations = order.reservations.filter(status=InventoryReservation.Status.ACTIVE)
    for reservation in reservations:
        if reservation.variant_id:
            updated = ProductVariant.objects.filter(
                pk=reservation.variant_id,
                reserved_quantity__gte=reservation.quantity,
            ).update(reserved_quantity=F("reserved_quantity") - reservation.quantity)
        else:
            updated = Product.objects.filter(
                pk=reservation.product_id,
                reserved_quantity__gte=reservation.quantity,
            ).update(reserved_quantity=F("reserved_quantity") - reservation.quantity)
        if not updated:
            raise OrderTransitionError("تعذر تحرير حجز المخزون بسبب عدم تطابق البيانات.")
        for allocation in reservation.batch_allocations.all():
            updated = InventoryBatch.objects.filter(
                pk=allocation.batch_id,
                reserved_quantity__gte=allocation.quantity,
            ).update(reserved_quantity=F("reserved_quantity") - allocation.quantity)
            if not updated:
                raise OrderTransitionError("تعذر تحرير حجز التشغيلة.")
        reservation.status = (
            InventoryReservation.Status.EXPIRED if expired else InventoryReservation.Status.RELEASED
        )
        reservation.save(update_fields=["status", "updated_at"])
    order.stock_released = True


def _consume_reservations(order):
    reservations = order.reservations.filter(status=InventoryReservation.Status.ACTIVE)
    if not reservations.exists():
        raise OrderTransitionError("لا يوجد حجز مخزون نشط لهذا الطلب.")
    for reservation in reservations:
        filters = {
            "pk": reservation.variant_id or reservation.product_id,
            "stock_quantity__gte": reservation.quantity,
            "reserved_quantity__gte": reservation.quantity,
        }
        model = ProductVariant if reservation.variant_id else Product
        updated = model.objects.filter(**filters).update(
            stock_quantity=F("stock_quantity") - reservation.quantity,
            reserved_quantity=F("reserved_quantity") - reservation.quantity,
        )
        if not updated:
            raise OrderTransitionError("تعذر خصم المخزون بسبب عدم تطابق البيانات.")
        for allocation in reservation.batch_allocations.all():
            updated = InventoryBatch.objects.filter(
                pk=allocation.batch_id,
                quantity__gte=allocation.quantity,
                reserved_quantity__gte=allocation.quantity,
            ).update(
                quantity=F("quantity") - allocation.quantity,
                reserved_quantity=F("reserved_quantity") - allocation.quantity,
            )
            if not updated:
                raise OrderTransitionError("تعذر خصم كمية التشغيلة.")
        reservation.status = InventoryReservation.Status.CONSUMED
        reservation.save(update_fields=["status", "updated_at"])
    order.stock_released = False


def _restore_consumed_reservations(order):
    """Restock a confirmed order that is cancelled before shipment."""
    for reservation in order.reservations.filter(status=InventoryReservation.Status.CONSUMED):
        model = ProductVariant if reservation.variant_id else Product
        target_id = reservation.variant_id or reservation.product_id
        model.objects.filter(pk=target_id).update(
            stock_quantity=F("stock_quantity") + reservation.quantity,
        )
        for allocation in reservation.batch_allocations.all():
            InventoryBatch.objects.filter(pk=allocation.batch_id).update(
                quantity=F("quantity") + allocation.quantity,
            )
        reservation.status = InventoryReservation.Status.RELEASED
        reservation.save(update_fields=["status", "updated_at"])
    order.stock_released = True


TRANSITIONS = {
    Order.Status.NEW: {Order.Status.CONFIRMED, Order.Status.CANCELLED},
    Order.Status.AWAITING_PAYMENT: {
        Order.Status.CONFIRMED,
        Order.Status.PAYMENT_FAILED,
        Order.Status.CANCELLED,
    },
    Order.Status.CONFIRMED: {Order.Status.PREPARING, Order.Status.CANCELLED},
    Order.Status.PREPARING: {Order.Status.SHIPPED, Order.Status.CANCELLED},
    Order.Status.SHIPPED: {Order.Status.DELIVERED},
    Order.Status.DELIVERED: {Order.Status.REFUNDED},
    Order.Status.CANCELLED: set(),
    Order.Status.PAYMENT_FAILED: set(),
    Order.Status.REFUNDED: set(),
}


def _set_sales_counted(order):
    if order.sales_counted:
        return
    for item in order.items.all():
        if item.product_id:
            Product.objects.filter(pk=item.product_id).update(sales_count=F("sales_count") + item.quantity)
    order.sales_counted = True


def transition_order(
    order,
    *,
    new_status,
    payment_status=None,
    payment_note=None,
    actor=None,
    ip_address=None,
):
    with transaction.atomic():
        order = Order.objects.prefetch_related(
            "items", "reservations__batch_allocations",
        ).get(pk=order.pk)
        old_status = order.status
        old_payment_status = order.payment_status
        new_payment_status = payment_status or old_payment_status
        if new_status != old_status and new_status not in TRANSITIONS.get(old_status, set()):
            raise OrderTransitionError(
                f"لا يمكن نقل الطلب من «{order.get_status_display()}» إلى الحالة المطلوبة."
            )
        if (
            new_status == Order.Status.CONFIRMED
            and order.payment_method == Order.PaymentMethod.INSTAPAY
            and new_payment_status != Order.PaymentStatus.VERIFIED
        ):
            raise OrderTransitionError("يجب تأكيد دفع InstaPay قبل تأكيد الطلب.")
        if new_payment_status == Order.PaymentStatus.REJECTED and new_status not in {
            Order.Status.PAYMENT_FAILED,
            Order.Status.CANCELLED,
        }:
            raise OrderTransitionError("رفض الدفع يتطلب نقل الطلب إلى «فشل الدفع» أو «ملغي».")

        if new_status == Order.Status.CONFIRMED and old_status != Order.Status.CONFIRMED:
            _consume_reservations(order)
            _consume_coupon(order)
        elif new_status in {Order.Status.CANCELLED, Order.Status.PAYMENT_FAILED} and new_status != old_status:
            _release_reservations(order)
            _restore_consumed_reservations(order)
            _release_coupon(order)
        if new_status == Order.Status.DELIVERED and old_status != Order.Status.DELIVERED:
            _set_sales_counted(order)

        order.status = new_status
        now = timezone.now()
        if new_status == Order.Status.CONFIRMED and not order.confirmed_at:
            order.confirmed_at = now
        elif new_status == Order.Status.SHIPPED and not order.shipped_at:
            order.shipped_at = now
        elif new_status == Order.Status.DELIVERED and not order.delivered_at:
            order.delivered_at = now
        elif new_status in {Order.Status.CANCELLED, Order.Status.PAYMENT_FAILED} and not order.cancelled_at:
            order.cancelled_at = now
        order.payment_status = new_payment_status
        if payment_note is not None:
            order.payment_note = payment_note
        order.save(update_fields=[
            "status", "payment_status", "payment_note", "stock_released",
            "coupon_consumed", "sales_counted", "updated_at",
            "confirmed_at", "shipped_at", "delivered_at", "cancelled_at",
        ])
        OrderAuditLog.objects.create(
            order=order,
            actor=actor,
            action="order_updated",
            old_values={"status": old_status, "payment_status": old_payment_status},
            new_values={"status": new_status, "payment_status": new_payment_status},
            note=payment_note or "",
            ip_address=ip_address,
        )
        transaction.on_commit(lambda: NotificationService.order_updated(order.pk, old_status))
        return order


def update_order_status(order, new_status, **kwargs):
    return transition_order(order, new_status=new_status, **kwargs)


def release_expired_reservations(now=None):
    now = now or timezone.now()
    order_ids = InventoryReservation.objects.filter(
        status=InventoryReservation.Status.ACTIVE,
        reserved_until__lte=now,
    ).values_list("order_id", flat=True).distinct()
    released = 0
    for order_id in order_ids.iterator():
        try:
            with transaction.atomic():
                order = Order.objects.prefetch_related("reservations__batch_allocations").get(pk=order_id)
                _release_reservations(order, expired=True)
                _release_coupon(order)
                order.status = (
                    Order.Status.PAYMENT_FAILED
                    if order.status == Order.Status.AWAITING_PAYMENT
                    else Order.Status.CANCELLED
                )
                order.save(update_fields=["status", "stock_released", "coupon_consumed", "updated_at"])
                OrderAuditLog.objects.create(
                    order=order,
                    action="reservation_expired",
                    new_values={"status": order.status},
                )
                released += 1
        except (Order.DoesNotExist, OrderTransitionError):
            logger.exception("Could not release expired reservation for order %s", order_id)
    return released


RETURN_TRANSITIONS = {
    ReturnRequest.Status.REQUESTED: {ReturnRequest.Status.APPROVED, ReturnRequest.Status.REJECTED},
    ReturnRequest.Status.APPROVED: {ReturnRequest.Status.RECEIVED, ReturnRequest.Status.REJECTED},
    ReturnRequest.Status.RECEIVED: {ReturnRequest.Status.REFUNDED},
    ReturnRequest.Status.REJECTED: set(),
    ReturnRequest.Status.REFUNDED: set(),
}


def process_return(return_request, *, new_status, refund_amount, admin_note, restockable, actor=None):
    with transaction.atomic():
        return_request = ReturnRequest.objects.select_related("order").prefetch_related(
            "items__order_item",
        ).get(pk=return_request.pk)
        old_status = return_request.status
        if new_status != old_status and new_status not in RETURN_TRANSITIONS.get(old_status, set()):
            raise OrderTransitionError("مسار حالة الإرجاع غير صحيح.")
        for item in return_request.items.all():
            item.restockable = bool(restockable.get(item.pk, item.restockable))
            item.save(update_fields=["restockable"])

        if new_status == ReturnRequest.Status.RECEIVED and old_status != new_status:
            for item in return_request.items.all():
                if not item.restockable or item.restocked:
                    continue
                target_model = ProductVariant if item.order_item.variant_id else Product
                target_id = item.order_item.variant_id or item.order_item.product_id
                if target_id:
                    target_model.objects.filter(pk=target_id).update(
                        stock_quantity=F("stock_quantity") + item.quantity,
                    )
                    item.restocked = True
                    item.save(update_fields=["restocked"])

        if new_status == ReturnRequest.Status.REFUNDED and old_status != new_status:
            if refund_amount <= 0:
                raise OrderTransitionError("أدخل مبلغ الرد قبل إتمام الاسترجاع.")
            order = return_request.order
            if order.refunded_amount + refund_amount > order.total:
                raise OrderTransitionError("مجموع المبالغ المستردة يتجاوز إجمالي الطلب.")
            order.refunded_amount += refund_amount
            if order.refunded_amount == order.total:
                order.status = Order.Status.REFUNDED
                order.payment_status = Order.PaymentStatus.REFUNDED
            order.save(update_fields=["refunded_amount", "status", "payment_status", "updated_at"])
            if order.sales_counted:
                for item in return_request.items.all():
                    if item.order_item.product_id:
                        Product.objects.filter(pk=item.order_item.product_id).update(
                            sales_count=Greatest(F("sales_count") - item.quantity, Value(0)),
                        )

        return_request.status = new_status
        return_request.refund_amount = refund_amount
        return_request.admin_note = admin_note
        return_request.save(update_fields=["status", "refund_amount", "admin_note", "updated_at"])
        OrderAuditLog.objects.create(
            order=return_request.order,
            actor=actor,
            action="return_updated",
            old_values={"return_status": old_status},
            new_values={"return_status": new_status, "refund_amount": str(refund_amount)},
            note=admin_note,
        )
        return return_request


class NotificationService:
    """Non-critical notification boundary; failures are logged after commit."""

    @staticmethod
    def _send(order, subject, body):
        if not order.email:
            return
        try:
            send_mail(subject, body, None, [order.email], fail_silently=False)
        except Exception:
            logger.exception("Order notification failed for %s", order.order_number)

    @classmethod
    def order_created(cls, order_id):
        try:
            order = Order.objects.get(pk=order_id)
        except Order.DoesNotExist:
            return
        cls._send(
            order,
            f"تم استلام طلبك {order.order_number}",
            f"استلمنا طلبك بإجمالي {order.total}. سنرسل لك أي تحديث على حالته.",
        )

    @classmethod
    def order_updated(cls, order_id, old_status):
        try:
            order = Order.objects.get(pk=order_id)
        except Order.DoesNotExist:
            return
        if order.status == old_status:
            return
        cls._send(
            order,
            f"تحديث الطلب {order.order_number}",
            f"أصبحت حالة طلبك: {order.get_status_display()}.",
        )
