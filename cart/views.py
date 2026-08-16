from django.contrib import messages
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from orders.models import Coupon
from products.models import Product, ProductVariant
from core.rate_limit import rate_limit
from core.utils import safe_redirect_target

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
    return redirect(safe_redirect_target(request, request.POST.get("next"), "cart:detail"))


@require_POST
def add(request, product_id):
    cart = Cart(request)
    product = get_object_or_404(Product.objects.active(), pk=product_id)
    variant = None
    if request.POST.get("variant_id"):
        variant = get_object_or_404(
            ProductVariant.objects.filter(product=product, is_active=True),
            pk=request.POST["variant_id"],
        )
    try:
        cart.add(product, max(1, int(request.POST.get("quantity", 1))), variant=variant)
    except (ValueError, TypeError) as exc:
        if request.headers.get("x-requested-with") == "XMLHttpRequest":
            return JsonResponse({"message": str(exc), "cart_count": len(cart)}, status=400)
        messages.error(request, str(exc))
        return redirect(safe_redirect_target(request, request.POST.get("next"), product.get_absolute_url()))
    return _response(request, "تمت إضافة المنتج إلى السلة.", cart)


@require_POST
def update(request, product_id):
    cart = Cart(request)
    product = get_object_or_404(Product, pk=product_id)
    variant = get_object_or_404(ProductVariant, pk=request.POST["variant_id"], product=product) if request.POST.get("variant_id") else None
    try:
        cart.add(product, int(request.POST.get("quantity", 1)), replace=True, variant=variant)
    except (ValueError, TypeError) as exc:
        messages.error(request, str(exc))
    else:
        messages.success(request, "تم تحديث السلة.")
    return redirect("cart:detail")


@require_POST
def remove(request, product_id):
    cart = Cart(request)
    product = get_object_or_404(Product, pk=product_id)
    variant = get_object_or_404(ProductVariant, pk=request.POST["variant_id"], product=product) if request.POST.get("variant_id") else None
    cart.remove(product, variant)
    return _response(request, "تمت إزالة المنتج من السلة.", cart)


@require_POST
@rate_limit("coupon", limit=10, window=300)
def apply_coupon(request):
    cart = Cart(request)
    code = request.POST.get("code", "").strip()
    coupon = Coupon.objects.filter(code__iexact=code).first()
    if not coupon:
        request.session.pop(Cart.COUPON_KEY, None)
        messages.error(request, "كود الخصم غير صالح أو انتهت صلاحيته.")
    else:
        request.session[Cart.COUPON_KEY] = coupon.code
        request.session.modified = True
        if cart.coupon:
            messages.success(request, "تم تطبيق كود الخصم.")
        else:
            request.session.pop(Cart.COUPON_KEY, None)
            messages.error(request, "الكود لا ينطبق على منتجات السلة أو تم بلوغ حد استخدامه.")
    request.session.modified = True
    return redirect("cart:detail")
