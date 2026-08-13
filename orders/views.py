from django.contrib import messages
from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render

from cart.cart import Cart
from core.models import StoreSettings

from .forms import CheckoutForm
from .models import Order, ShippingZone
from .services import CheckoutError, calculate_shipping, create_order


def checkout(request):
    cart = Cart(request)
    if len(cart) == 0:
        messages.info(request, "أضف منتجات إلى السلة قبل إتمام الطلب.")
        return redirect("products:list")
    initial = {}
    if request.user.is_authenticated:
        initial = {
            "full_name": request.user.get_full_name(),
            "phone": getattr(getattr(request.user, "profile", None), "phone", ""),
        }
    form = CheckoutForm(request.POST or None, request.FILES or None, initial=initial)
    if request.method == "POST" and form.is_valid():
        try:
            order = create_order(form=form, cart=cart, user=request.user)
        except CheckoutError as exc:
            messages.error(request, str(exc))
        else:
            return redirect(f"{order.get_success_url()}?token={order.access_token}")
    return render(request, "orders/checkout.html", {
        "form": form,
        "cart": cart,
        "settings": StoreSettings.load(),
    })


def shipping_quote(request):
    zone = get_object_or_404(ShippingZone, pk=request.GET.get("zone"), is_active=True)
    cart = Cart(request)
    shipping = calculate_shipping(cart.total_after_discount, zone)
    return JsonResponse({
        "shipping": str(shipping),
        "subtotal": str(cart.subtotal),
        "discount": str(cart.discount),
        "total": str(cart.total_after_discount + shipping),
    })


def success(request, order_number):
    order = get_object_or_404(Order.objects.prefetch_related("items"), order_number=order_number)
    owns_order = request.user.is_authenticated and order.user_id == request.user.id
    token_matches = str(order.access_token) == request.GET.get("token", "")
    if not owns_order and not token_matches:
        raise Http404
    return render(request, "orders/success.html", {"order": order})


def order_detail(request, order_number):
    if not request.user.is_authenticated:
        return redirect("accounts:login")
    order = get_object_or_404(
        Order.objects.prefetch_related("items"), order_number=order_number, user=request.user
    )
    return render(request, "orders/detail.html", {"order": order})
