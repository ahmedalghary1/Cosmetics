from datetime import timedelta

from django.contrib import messages
from django.contrib.auth import get_user_model
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Count, DecimalField, Q, Sum, Value
from django.db.models.deletion import ProtectedError
from django.db.models.functions import Coalesce
from django.http import HttpResponseNotAllowed
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from core.models import Banner, ContactMessage, ContentPage, RoutineStep, SocialGalleryImage, StoreSettings
from core.validators import validate_image_upload
from core.image_utils import optimize_uploaded_image
from orders.models import Coupon, Order, ShippingZone
from orders.services import update_order_status
from products.models import Category, Product, ProductImage

from .forms import (
    BannerForm, CategoryForm, ContentPageForm, CouponForm, OrderUpdateForm,
    ProductForm, RoutineStepForm, ShippingZoneForm, SocialGalleryForm, StoreSettingsForm,
)
from .decorators import staff_required


PAGE_SIZE = 15


def paginate(request, queryset, per_page=PAGE_SIZE):
    return Paginator(queryset, per_page).get_page(request.GET.get("page"))


@staff_required
def home(request):
    today = timezone.localdate()
    orders = Order.objects.all()
    context = {
        "today_orders": orders.filter(created_at__date=today).count(),
        "new_orders": orders.filter(status=Order.Status.NEW).count(),
        "total_orders": orders.count(),
        "sales": orders.exclude(status=Order.Status.CANCELLED).aggregate(
            amount=Coalesce(Sum("total"), Value(0), output_field=DecimalField(max_digits=12, decimal_places=2))
        )["amount"],
        "pending_payments": orders.filter(payment_status=Order.PaymentStatus.PENDING).count(),
        "low_stock": Product.objects.filter(is_active=True, stock_quantity__gt=0, stock_quantity__lte=5).count(),
        "out_of_stock": Product.objects.filter(is_active=True, stock_quantity=0).count(),
        "customers": get_user_model().objects.filter(is_staff=False).count(),
        "latest_orders": orders.select_related("governorate")[:8],
    }
    return render(request, "dashboard/home.html", context)


@staff_required
def product_list(request):
    products = Product.objects.select_related("category")
    query = request.GET.get("q", "").strip()
    if query:
        products = products.filter(Q(name__icontains=query) | Q(sku__icontains=query))
    category = request.GET.get("category")
    if category:
        products = products.filter(category_id=category)
    return render(request, "dashboard/products.html", {
        "page_obj": paginate(request, products),
        "categories": Category.objects.all(),
        "query": query,
    })


@staff_required
def product_form(request, pk=None):
    product = get_object_or_404(Product, pk=pk) if pk else None
    form = ProductForm(request.POST or None, request.FILES or None, instance=product)
    if request.method == "POST" and form.is_valid():
        try:
            optimized_images = []
            for image in request.FILES.getlist("additional_images"):
                validate_image_upload(image)
                optimized_images.append(optimize_uploaded_image(image))
            with transaction.atomic():
                product = form.save()
                product.images.filter(pk__in=request.POST.getlist("delete_images")).delete()
                start_order = product.images.count()
                for index, image in enumerate(optimized_images, start_order):
                    ProductImage.objects.create(
                        product=product, image=image, alt_text=product.name, order=index,
                    )
        except Exception as exc:
            messages.error(request, str(exc))
        else:
            messages.success(request, "تم حفظ المنتج بنجاح.")
            return redirect("dashboard:products")
    return render(request, "dashboard/form.html", {
        "form": form, "title": "تعديل المنتج" if product else "إضافة منتج",
        "product": product, "additional_images": True,
    })


@staff_required
@require_POST
def product_delete(request, pk):
    product = get_object_or_404(Product, pk=pk)
    product.delete()
    messages.success(request, "تم حذف المنتج.")
    return redirect("dashboard:products")


@staff_required
@require_POST
def product_toggle(request, pk):
    product = get_object_or_404(Product, pk=pk)
    product.is_active = not product.is_active
    product.save(update_fields=["is_active", "updated_at"])
    messages.success(request, "تم تحديث حالة المنتج.")
    return redirect("dashboard:products")


@staff_required
def inventory(request):
    products = Product.objects.select_related("category").order_by("stock_quantity", "name")
    return render(request, "dashboard/inventory.html", {"page_obj": paginate(request, products)})


@staff_required
def category_list(request):
    return render(request, "dashboard/categories.html", {"categories": Category.objects.all()})


@staff_required
def category_form(request, pk=None):
    instance = get_object_or_404(Category, pk=pk) if pk else None
    form = CategoryForm(request.POST or None, request.FILES or None, instance=instance)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "تم حفظ التصنيف.")
        return redirect("dashboard:categories")
    return render(request, "dashboard/form.html", {"form": form, "title": "تعديل تصنيف" if instance else "إضافة تصنيف"})


@staff_required
@require_POST
def category_delete(request, pk):
    category = get_object_or_404(Category, pk=pk)
    if category.products.exists():
        messages.error(request, "لا يمكن حذف تصنيف يحتوي على منتجات.")
    else:
        category.delete()
        messages.success(request, "تم حذف التصنيف.")
    return redirect("dashboard:categories")


@staff_required
def order_list(request):
    orders = Order.objects.select_related("governorate")
    query = request.GET.get("q", "").strip()
    if query:
        orders = orders.filter(Q(order_number__icontains=query) | Q(full_name__icontains=query) | Q(phone__icontains=query))
    for field in ["status", "payment_method", "payment_status"]:
        value = request.GET.get(field)
        if value:
            orders = orders.filter(**{field: value})
    period = request.GET.get("period")
    now = timezone.now()
    if period == "today":
        orders = orders.filter(created_at__date=timezone.localdate())
    elif period == "week":
        orders = orders.filter(created_at__gte=now - timedelta(days=7))
    elif period == "month":
        orders = orders.filter(created_at__gte=now - timedelta(days=30))
    return render(request, "dashboard/orders.html", {
        "page_obj": paginate(request, orders), "order_statuses": Order.Status.choices,
        "payment_methods": Order.PaymentMethod.choices, "payment_statuses": Order.PaymentStatus.choices,
    })


@staff_required
def order_detail(request, pk):
    order = get_object_or_404(Order.objects.select_related("governorate", "user").prefetch_related("items"), pk=pk)
    original_status = order.status
    form = OrderUpdateForm(request.POST or None, instance=order)
    if request.method == "POST" and form.is_valid():
        new_status = form.cleaned_data["status"]
        order.status = original_status
        order.payment_status = form.cleaned_data["payment_status"]
        order.payment_note = form.cleaned_data["payment_note"]
        order.save(update_fields=["payment_status", "payment_note", "updated_at"])
        if new_status != original_status:
            try:
                order = update_order_status(order, new_status)
            except ValueError as exc:
                messages.error(request, str(exc))
                return redirect("dashboard:order_detail", pk=order.pk)
        messages.success(request, "تم تحديث الطلب.")
        return redirect("dashboard:order_detail", pk=order.pk)
    return render(request, "dashboard/order_detail.html", {"order": order, "form": form})


@staff_required
def payments(request):
    orders = Order.objects.filter(payment_method=Order.PaymentMethod.INSTAPAY).select_related("governorate")
    status = request.GET.get("status")
    if status:
        orders = orders.filter(payment_status=status)
    return render(request, "dashboard/payments.html", {
        "page_obj": paginate(request, orders), "payment_statuses": Order.PaymentStatus.choices,
    })


@staff_required
def user_list(request):
    users = get_user_model().objects.annotate(order_count=Count("orders")).order_by("-date_joined")
    query = request.GET.get("q", "").strip()
    if query:
        users = users.filter(Q(username__icontains=query) | Q(first_name__icontains=query) | Q(email__icontains=query))
    return render(request, "dashboard/users.html", {"page_obj": paginate(request, users)})


@staff_required
def user_detail(request, pk):
    user = get_object_or_404(get_user_model(), pk=pk)
    return render(request, "dashboard/user_detail.html", {"customer": user, "orders": user.orders.all()[:20]})


@staff_required
@require_POST
def user_toggle(request, pk):
    user = get_object_or_404(get_user_model(), pk=pk)
    if user == request.user:
        messages.error(request, "لا يمكنك تعطيل حسابك الحالي.")
    else:
        user.is_active = not user.is_active
        user.save(update_fields=["is_active"])
        messages.success(request, "تم تحديث حالة المستخدم.")
    return redirect("dashboard:user_detail", pk=pk)


def _model_list(request, model, template, context_name):
    return render(request, template, {context_name: model.objects.all()})


def _model_form(request, form_class, success_url, title, instance=None):
    form = form_class(request.POST or None, request.FILES or None, instance=instance)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "تم الحفظ بنجاح.")
        return redirect(success_url)
    return render(request, "dashboard/form.html", {"form": form, "title": title})


@staff_required
def shipping_list(request):
    return _model_list(request, ShippingZone, "dashboard/simple_list.html", "objects")


@staff_required
def shipping_form(request, pk=None):
    instance = get_object_or_404(ShippingZone, pk=pk) if pk else None
    return _model_form(request, ShippingZoneForm, "dashboard:shipping", "منطقة شحن", instance)


@staff_required
def coupon_list(request):
    return render(request, "dashboard/coupons.html", {"coupons": Coupon.objects.all()})


@staff_required
def coupon_form(request, pk=None):
    instance = get_object_or_404(Coupon, pk=pk) if pk else None
    return _model_form(request, CouponForm, "dashboard:coupons", "كوبون خصم", instance)


@staff_required
def banner_list(request):
    return render(request, "dashboard/banners.html", {"banners": Banner.objects.all()})


@staff_required
def banner_form(request, pk=None):
    instance = get_object_or_404(Banner, pk=pk) if pk else None
    return _model_form(request, BannerForm, "dashboard:banners", "بانر", instance)


@staff_required
def page_list(request):
    return render(request, "dashboard/pages.html", {"pages": ContentPage.objects.all()})


@staff_required
def page_form(request, pk=None):
    instance = get_object_or_404(ContentPage, pk=pk) if pk else None
    return _model_form(request, ContentPageForm, "dashboard:pages", "صفحة محتوى", instance)


@staff_required
def gallery_list(request):
    return render(request, "dashboard/gallery.html", {"gallery_items": SocialGalleryImage.objects.all()})


@staff_required
def gallery_form(request, pk=None):
    instance = get_object_or_404(SocialGalleryImage, pk=pk) if pk else None
    return _model_form(request, SocialGalleryForm, "dashboard:gallery", "صورة المعرض", instance)


@staff_required
def routine_list(request):
    return render(request, "dashboard/routine.html", {"routine_steps": RoutineStep.objects.select_related("category", "product")})


@staff_required
def routine_form(request, pk=None):
    instance = get_object_or_404(RoutineStep, pk=pk) if pk else None
    return _model_form(request, RoutineStepForm, "dashboard:routine", "خطوة روتين", instance)


@staff_required
def settings_edit(request):
    settings = StoreSettings.load()
    form = StoreSettingsForm(request.POST or None, request.FILES or None, instance=settings)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "تم حفظ إعدادات المتجر.")
        return redirect("dashboard:settings")
    return render(request, "dashboard/form.html", {"form": form, "title": "إعدادات المتجر"})


@staff_required
def messages_list(request):
    return render(request, "dashboard/messages.html", {"contact_messages": ContactMessage.objects.all()})


@staff_required
def message_detail(request, pk):
    contact = get_object_or_404(ContactMessage, pk=pk)
    if not contact.is_read:
        contact.is_read = True
        contact.save(update_fields=["is_read", "updated_at"])
    return render(request, "dashboard/message_detail.html", {"contact": contact})


@staff_required
@require_POST
def generic_delete(request, model_name, pk):
    models = {
        "shipping": (ShippingZone, "dashboard:shipping"),
        "coupon": (Coupon, "dashboard:coupons"),
        "banner": (Banner, "dashboard:banners"),
        "page": (ContentPage, "dashboard:pages"),
        "gallery": (SocialGalleryImage, "dashboard:gallery"),
        "routine": (RoutineStep, "dashboard:routine"),
    }
    if model_name not in models:
        return HttpResponseNotAllowed(["POST"])
    model, redirect_name = models[model_name]
    try:
        get_object_or_404(model, pk=pk).delete()
    except ProtectedError:
        messages.error(request, "لا يمكن حذف هذا العنصر لأنه مرتبط بطلبات أو بيانات أخرى.")
    else:
        messages.success(request, "تم الحذف بنجاح.")
    return redirect(redirect_name)
