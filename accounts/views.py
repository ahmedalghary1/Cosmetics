from django.contrib import messages
from django.contrib.auth import login, update_session_auth_hash, views as auth_views
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST
from django.utils.decorators import method_decorator

from products.models import Product
from core.models import StoreSettings
from core.rate_limit import rate_limit
from core.utils import safe_redirect_target

from .forms import ArabicAuthenticationForm, ArabicPasswordChangeForm, ProfileForm, RegistrationForm
from .models import WishlistItem


@method_decorator(rate_limit("login", limit=10, window=300), name="dispatch")
class RateLimitedLoginView(auth_views.LoginView):
    template_name = "registration/login.html"
    authentication_form = ArabicAuthenticationForm


@method_decorator(rate_limit("password-reset", limit=5, window=3600), name="dispatch")
class BrandedPasswordResetView(auth_views.PasswordResetView):
    template_name = "registration/password_reset_form.html"
    email_template_name = "registration/password_reset_email.html"
    html_email_template_name = "registration/password_reset_email_html.html"
    subject_template_name = "registration/password_reset_subject.txt"

    def dispatch(self, request, *args, **kwargs):
        self.extra_email_context = {"store_name": StoreSettings.load().store_name}
        return super().dispatch(request, *args, **kwargs)


@rate_limit("register", limit=5, window=3600)
def register(request):
    if request.user.is_authenticated:
        return redirect("accounts:profile")
    form = RegistrationForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        user = form.save()
        login(request, user)
        messages.success(request, "تم إنشاء الحساب بنجاح.")
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
        messages.success(request, "تم تحديث البيانات.")
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
    items = request.user.wishlist_items.filter(
        product__is_active=True, product__category__is_active=True,
    ).select_related("product", "product__category")
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
    return redirect(safe_redirect_target(request, request.POST.get("next"), "accounts:wishlist"))
