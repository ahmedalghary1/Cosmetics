from datetime import date
from decimal import Decimal
import secrets

from django.db import transaction
from django.db.models import F, Value
from django.db.models.functions import Greatest

from core.models import StoreSettings
from products.models import Product

from .models import Coupon, Order, OrderItem


class CheckoutError(Exception):
    pass


def calculate_shipping(subtotal_after_discount, zone):
    threshold = StoreSettings.load().free_shipping_threshold
    if threshold is not None and subtotal_after_discount >= threshold:
        return Decimal("0.00")
    return zone.shipping_cost


def build_order_number():
    return f"ORD-{date.today():%y%m%d}-{secrets.token_hex(3).upper()}"


@transaction.atomic
def create_order(*, form, cart, user=None):
    cart_items = list(cart)
    if not cart_items:
        raise CheckoutError("سلة التسوق فارغة.")
    requested = {item["product"].pk: item["quantity"] for item in cart_items}
    locked = {
        product.pk: product
        for product in Product.objects.select_for_update().filter(pk__in=requested, is_active=True)
    }
    if set(locked) != set(requested):
        raise CheckoutError("أحد المنتجات لم يعد متاحًا. حدّث السلة وحاول مرة أخرى.")

    subtotal = Decimal("0.00")
    for product_id, quantity in requested.items():
        product = locked[product_id]
        if quantity > product.stock_quantity:
            raise CheckoutError(f"المتوفر من «{product.name}» هو {product.stock_quantity} فقط.")
        subtotal += product.price * quantity

    coupon = cart.coupon
    if coupon:
        coupon = Coupon.objects.select_for_update().get(pk=coupon.pk)
        if not coupon.is_valid_for(subtotal):
            coupon = None
    discount = coupon.calculate_discount(subtotal) if coupon else Decimal("0.00")
    shipping = calculate_shipping(subtotal - discount, form.cleaned_data["governorate"])
    payment_method = form.cleaned_data["payment_method"]
    payment_status = (
        Order.PaymentStatus.PENDING
        if payment_method == Order.PaymentMethod.INSTAPAY
        else Order.PaymentStatus.UNPAID
    )

    order = form.save(commit=False)
    order.order_number = build_order_number()
    order.user = user if user and user.is_authenticated else None
    order.subtotal = subtotal
    order.discount = discount
    order.shipping_cost = shipping
    order.total = subtotal - discount + shipping
    order.coupon = coupon
    order.payment_status = payment_status
    order.save()

    order_items = []
    for product_id, quantity in requested.items():
        product = locked[product_id]
        order_items.append(OrderItem(
            order=order,
            product=product,
            product_name=product.name,
            sku=product.sku,
            quantity=quantity,
            unit_price=product.price,
            total_price=product.price * quantity,
        ))
        Product.objects.filter(pk=product.pk).update(
            stock_quantity=F("stock_quantity") - quantity,
            sales_count=F("sales_count") + quantity,
        )
    OrderItem.objects.bulk_create(order_items)
    if coupon:
        Coupon.objects.filter(pk=coupon.pk).update(used_count=F("used_count") + 1)
    transaction.on_commit(cart.clear)
    return order


@transaction.atomic
def update_order_status(order, new_status):
    order = Order.objects.select_for_update().prefetch_related("items").get(pk=order.pk)
    if order.status in {Order.Status.CANCELLED, Order.Status.DELIVERED} and new_status != order.status:
        raise ValueError("لا يمكن تغيير طلب وصل إلى حالة نهائية.")
    if new_status == Order.Status.CANCELLED and order.status == Order.Status.SHIPPED:
        raise ValueError("لا يمكن إلغاء طلب تم شحنه. عالج الاسترجاع خارج مسار الإلغاء.")
    if new_status == Order.Status.CANCELLED and order.status != Order.Status.CANCELLED and not order.stock_released:
        for item in order.items.all():
            if item.product_id:
                Product.objects.filter(pk=item.product_id).update(
                    stock_quantity=F("stock_quantity") + item.quantity,
                    sales_count=Greatest(F("sales_count") - item.quantity, Value(0)),
                )
        order.stock_released = True
    order.status = new_status
    order.save(update_fields=["status", "stock_released", "updated_at"])
    return order
