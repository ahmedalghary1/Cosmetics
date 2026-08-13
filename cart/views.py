from django.contrib import messages
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from orders.models import Coupon
from products.models import Product

from .cart import Cart


def detail(request):
    return render(request, "cart/detail.html", {"cart": Cart(request)})


def _response(request, message, cart, status=200):
    if request.headers.get("x-requested-with") == "XMLHttpRequest":
        return JsonResponse({
            "message": message,
            "cart_count": len(cart),
            "subtotal": str(cart.subtotal),
            "discount": str(cart.discount),
            "total": str(cart.total_after_discount),
        }, status=status)
    messages.success(request, message)
    return redirect(request.POST.get("next") or "cart:detail")


@require_POST
def add(request, product_id):
    cart = Cart(request)
    product = get_object_or_404(Product.objects.active(), pk=product_id)
    try:
        cart.add(product, max(1, int(request.POST.get("quantity", 1))))
    except (ValueError, TypeError) as exc:
        if request.headers.get("x-requested-with") == "XMLHttpRequest":
            return JsonResponse({"message": str(exc), "cart_count": len(cart)}, status=400)
        messages.error(request, str(exc))
        return redirect(request.POST.get("next") or product.get_absolute_url())
    return _response(request, "تمت إضافة المنتج إلى السلة.", cart)


@require_POST
def update(request, product_id):
    cart = Cart(request)
    product = get_object_or_404(Product, pk=product_id)
    try:
        cart.add(product, int(request.POST.get("quantity", 1)), replace=True)
    except (ValueError, TypeError) as exc:
        messages.error(request, str(exc))
    else:
        messages.success(request, "تم تحديث السلة.")
    return redirect("cart:detail")


@require_POST
def remove(request, product_id):
    cart = Cart(request)
    product = get_object_or_404(Product, pk=product_id)
    cart.remove(product)
    return _response(request, "تمت إزالة المنتج من السلة.", cart)


@require_POST
def apply_coupon(request):
    cart = Cart(request)
    code = request.POST.get("code", "").strip()
    coupon = Coupon.objects.filter(code__iexact=code).first()
    if not coupon or not coupon.is_valid_for(cart.subtotal):
        request.session.pop(Cart.COUPON_KEY, None)
        messages.error(request, "كود الخصم غير صالح أو انتهت صلاحيته.")
    else:
        request.session[Cart.COUPON_KEY] = coupon.code
        messages.success(request, "تم تطبيق كود الخصم.")
    request.session.modified = True
    return redirect("cart:detail")
