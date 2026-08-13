from django.contrib import messages
from django.contrib.auth import login, update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from products.models import Product

from .forms import ArabicPasswordChangeForm, ProfileForm, RegistrationForm
from .models import WishlistItem


def register(request):
    if request.user.is_authenticated:
        return redirect("accounts:profile")
    form = RegistrationForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        user = form.save()
        login(request, user)
        messages.success(request, "تم إنشاء حسابك بنجاح.")
        return redirect("accounts:profile")
    return render(request, "accounts/register.html", {"form": form})


@login_required
def profile(request):
    orders = request.user.orders.prefetch_related("items")[:10]
    return render(request, "accounts/profile.html", {"orders": orders})


@login_required
def edit_profile(request):
    profile_obj = getattr(request.user, "profile", None)
    initial = {
        "full_name": request.user.get_full_name(),
        "phone": getattr(profile_obj, "phone", ""),
        "email": request.user.email,
    }
    form = ProfileForm(request.POST or None, user=request.user, initial=initial)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "تم تحديث بياناتك.")
        return redirect("accounts:profile")
    return render(request, "accounts/edit_profile.html", {"form": form})


@login_required
def change_password(request):
    form = ArabicPasswordChangeForm(request.user, request.POST or None)
    if request.method == "POST" and form.is_valid():
        user = form.save()
        update_session_auth_hash(request, user)
        messages.success(request, "تم تغيير كلمة المرور بنجاح.")
        return redirect("accounts:profile")
    return render(request, "accounts/change_password.html", {"form": form})


@login_required
def wishlist(request):
    items = request.user.wishlist_items.select_related("product", "product__category")
    return render(request, "accounts/wishlist.html", {"wishlist_items": items})


@login_required
@require_POST
def wishlist_toggle(request, product_id):
    product = get_object_or_404(Product.objects.active(), pk=product_id)
    item, created = WishlistItem.objects.get_or_create(user=request.user, product=product)
    if created:
        message = "تمت إضافة المنتج إلى المفضلة."
        active = True
    else:
        item.delete()
        message = "تمت إزالة المنتج من المفضلة."
        active = False
    if request.headers.get("x-requested-with") == "XMLHttpRequest":
        return JsonResponse({"message": message, "active": active})
    messages.success(request, message)
    return redirect(request.POST.get("next") or "accounts:wishlist")
