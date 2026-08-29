from django.contrib import messages
from django.contrib.auth.decorators import login_required
from datetime import timedelta
import uuid
from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from cart.cart import Cart
from core.models import StoreSettings
from core.rate_limit import rate_limit

from .forms import CheckoutForm, ReturnRequestForm, ShippingQuoteForm
from .models import Order, ShippingZone
from .services import CheckoutError, calculate_shipping, create_order


@rate_limit("checkout", limit=5, window=900)
def checkout(request):
    cart = Cart(request)
    store_settings = StoreSettings.load()
    checkout_key = request.session.get("checkout_idempotency_key")
    if not checkout_key:
        checkout_key = str(uuid.uuid4())
        request.session["checkout_idempotency_key"] = checkout_key
    posted_key = request.POST.get("idempotency_key", "")
    if request.method == "POST" and posted_key == checkout_key:
        existing = Order.objects.filter(idempotency_key=posted_key).first()
        if existing:
            return redirect(f"{existing.get_success_url()}?token={existing.access_token}")
    if len(cart) == 0:
        messages.info(request, "أضف منتجات إلى السلة قبل إتمام الطلب.")
        return redirect("products:list")
    initial = {}
    if request.user.is_authenticated:
        initial = {
            "full_name": request.user.get_full_name(),
            "email": request.user.email,
            "phone": getattr(getattr(request.user, "profile", None), "phone", ""),
        }
    form = CheckoutForm(
        request.POST or None,
        request.FILES or None,
        initial=initial,
        store_settings=store_settings,
    )
    if request.method == "POST" and form.is_valid():
        if posted_key != checkout_key:
            messages.error(request, "انتهت صلاحية جلسة الدفع. يرجى إعادة فتح صفحة إتمام الطلب.")
        else:
            try:
                order = create_order(
                    form=form,
                    cart=cart,
                    user=request.user,
                    idempotency_key=posted_key,
                )
            except CheckoutError as exc:
                messages.error(request, str(exc))
            else:
                request.session.pop("checkout_idempotency_key", None)
                return redirect(f"{order.get_success_url()}?token={order.access_token}")
    return render(request, "orders/checkout.html", {
        "form": form,
        "cart": cart,
        "settings": store_settings,
        "idempotency_key": checkout_key,
    })


@rate_limit("shipping-quote", limit=60, window=60, methods=("GET",))
def shipping_quote(request):
    form = ShippingQuoteForm(request.GET)
    if not form.is_valid():
        return JsonResponse({"message": "يرجى اختيار محافظة صحيحة."}, status=400)
    zone = form.cleaned_data["zone"]
    cart = Cart(request)
    shipping = calculate_shipping(cart.total_after_discount, zone)
    return JsonResponse({
        "shipping": str(shipping),
        "subtotal": str(cart.subtotal),
        "discount": str(cart.discount),
        "total": str(cart.total_after_discount + shipping),
        "delivery_min_days": zone.estimated_delivery_min_days,
        "delivery_max_days": zone.estimated_delivery_max_days,
    })


def success(request, order_number):
    order = get_object_or_404(
        Order.objects.prefetch_related("items__bundle_components"), order_number=order_number,
    )
    owns_order = request.user.is_authenticated and order.user_id == request.user.id
    token_matches = str(order.access_token) == request.GET.get("token", "")
    if not owns_order and not token_matches:
        raise Http404
    purchase_event = {
        "transaction_id": order.order_number,
        "currency": "EGP",
        "value": float(order.total),
        "shipping": float(order.shipping_cost),
        "coupon": order.coupon.code if order.coupon_id else "",
        "items": [
            {
                "item_id": item.sku,
                "item_name": item.product_name,
                "price": float(item.unit_price),
                "quantity": item.quantity,
            }
            for item in order.items.all()
        ],
    }
    return render(request, "orders/success.html", {"order": order, "purchase_event": purchase_event})


def order_detail(request, order_number):
    if not request.user.is_authenticated:
        return redirect("accounts:login")
    order = get_object_or_404(
        Order.objects.prefetch_related("items__bundle_components"),
        order_number=order_number,
        user=request.user,
    )
    return render(request, "orders/detail.html", {"order": order})


@login_required(login_url="accounts:login")
@rate_limit("return-request", limit=5, window=3600)
def request_return(request, order_number):
    order = get_object_or_404(
        Order.objects.prefetch_related("items"),
        order_number=order_number,
        user=request.user,
    )
    settings = StoreSettings.load()
    deadline = (order.delivered_at or order.updated_at) + timedelta(days=settings.return_window_days)
    if order.status not in {Order.Status.DELIVERED, Order.Status.REFUNDED} or timezone.now() > deadline:
        messages.error(request, "هذا الطلب غير متاح للإرجاع أو انتهت مدة الإرجاع.")
        return redirect("orders:detail", order_number=order.order_number)
    form = ReturnRequestForm(request.POST or None, order=order)
    if request.method == "POST" and form.is_valid():
        form.save(user=request.user)
        messages.success(request, "تم إرسال طلب الإرجاع للمراجعة.")
        return redirect("orders:detail", order_number=order.order_number)
    return render(request, "orders/return_form.html", {"form": form, "order": order, "deadline": deadline})
