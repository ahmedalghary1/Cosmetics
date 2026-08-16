from datetime import timedelta
import csv
import mimetypes
from pathlib import Path

from django.contrib import messages
from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Count, DecimalField, F, Q, Sum, Value
from django.db.models.deletion import ProtectedError
from django.db.models.functions import Coalesce
from django.http import FileResponse, Http404, HttpResponse, HttpResponseNotAllowed
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from core.models import Banner, ContactMessage, ContentPage, Offer, RoutineStep, SocialGalleryImage, StoreSettings
from core.rate_limit import rate_limit
from core.validators import validate_image_upload
from core.image_utils import optimize_uploaded_image
from orders.models import Coupon, Order, ReturnRequest, ReturnRequestItem, ShippingZone
from orders.services import OrderTransitionError, process_return, transition_order
from products.models import Category, InventoryBatch, Product, ProductImage, ProductVariant, VariantOption

from .forms import (
    BannerForm, CategoryForm, ContentPageForm, CouponForm, OfferForm, OrderUpdateForm,
    InventoryBatchForm, ProductForm, ProductVariantForm, RoutineStepForm, ShippingZoneForm,
    ReturnUpdateForm, SocialGalleryForm, StoreSettingsForm, UserRoleForm, VariantOptionForm,
)
from .decorators import dashboard_permission, staff_required


PAGE_SIZE = 15


def paginate(request, queryset, per_page=PAGE_SIZE):
    page = Paginator(queryset, per_page).get_page(request.GET.get("page"))
    query = request.GET.copy()
    query.pop("page", None)
    page.query_string = query.urlencode()
    return page


@staff_required
def export_csv(request, report):
    reports = {
        "orders": "orders.view_order",
        "products": "products.view_product",
        "inventory": "products.view_inventorybatch",
        "customers": "accounts.export_customer_data",
    }
    permission = reports.get(report)
    if not permission:
        raise Http404
    if not request.user.is_superuser and not request.user.has_perm(permission):
        raise PermissionDenied
    response = HttpResponse(content_type="text/csv; charset=utf-8")
    response.write("\ufeff")
    response["Content-Disposition"] = f'attachment; filename="{report}-{timezone.localdate()}.csv"'
    writer = csv.writer(response)
    if report == "orders":
        writer.writerow(["رقم الطلب", "التاريخ", "العميل", "الهاتف", "الحالة", "حالة الدفع", "الإجمالي", "المسترد"])
        for order in Order.objects.iterator():
            writer.writerow([order.order_number, order.created_at, order.full_name, order.phone, order.get_status_display(), order.get_payment_status_display(), order.total, order.refunded_amount])
    elif report == "products":
        writer.writerow(["SKU", "المنتج", "التصنيف", "السعر", "المخزون", "المحجوز", "نشط"])
        for product in Product.objects.select_related("category").iterator():
            writer.writerow([product.sku, product.name, product.category.name, product.price, product.stock_quantity, product.reserved_quantity, product.is_active])
    elif report == "inventory":
        writer.writerow(["المنتج", "الخيار", "التشغيلة", "الكمية", "المحجوز", "الصلاحية", "التكلفة"])
        for batch in InventoryBatch.objects.select_related("product", "variant").iterator():
            writer.writerow([batch.product.name, batch.variant.option_summary if batch.variant else "", batch.batch_number, batch.quantity, batch.reserved_quantity, batch.expiry_date, batch.purchase_cost])
    else:
        writer.writerow(["اسم المستخدم", "الاسم", "البريد", "الهاتف", "تاريخ التسجيل", "نشط"])
        for user in get_user_model().objects.select_related("profile").iterator():
            writer.writerow([user.username, user.get_full_name(), user.email, getattr(user.profile, "phone", ""), user.date_joined, user.is_active])
    return response


@staff_required
def home(request):
    if not request.user.is_superuser and not request.user.get_all_permissions():
        raise PermissionDenied
    today = timezone.localdate()
    orders = Order.objects.all()
    recognized = orders.filter(status__in=[Order.Status.DELIVERED, Order.Status.REFUNDED])
    money_field = DecimalField(max_digits=14, decimal_places=2)
    recognized_totals = recognized.aggregate(
        gross=Coalesce(Sum("total"), Value(0), output_field=money_field),
        refunds=Coalesce(Sum("refunded_amount"), Value(0), output_field=money_field),
    )
    cogs = Order.objects.filter(
        status__in=[Order.Status.DELIVERED, Order.Status.REFUNDED],
    ).aggregate(
        amount=Coalesce(Sum("items__total_cost"), Value(0), output_field=money_field),
    )["amount"]
    returned_cogs = ReturnRequestItem.objects.filter(
        return_request__status=ReturnRequest.Status.REFUNDED,
    ).aggregate(
        amount=Coalesce(
            Sum(F("order_item__unit_cost") * F("quantity"), output_field=money_field),
            Value(0),
            output_field=money_field,
        ),
    )["amount"]
    net_cogs = cogs - returned_cogs
    net_sales = recognized_totals["gross"] - recognized_totals["refunds"]
    recognized_count = recognized.count()
    paid_sales = orders.filter(
        Q(payment_status__in=[Order.PaymentStatus.VERIFIED, Order.PaymentStatus.REFUNDED])
        | Q(status__in=[Order.Status.DELIVERED, Order.Status.REFUNDED])
    ).exclude(status__in=[Order.Status.CANCELLED, Order.Status.PAYMENT_FAILED]).aggregate(
        amount=Coalesce(Sum("total"), Value(0), output_field=money_field),
    )["amount"]
    can_view_orders = request.user.is_superuser or request.user.has_perm("orders.view_order")
    can_view_financial = request.user.is_superuser or request.user.has_perm("orders.view_financial_reports")
    can_view_inventory = request.user.is_superuser or request.user.has_perm("products.view_product")
    can_view_customers = request.user.is_superuser or request.user.has_perm("auth.view_user")
    context = {
        "today_orders": orders.filter(created_at__date=today).count(),
        "new_orders": orders.filter(status__in=[Order.Status.NEW, Order.Status.AWAITING_PAYMENT]).count(),
        "total_orders": orders.count(),
        "sales": net_sales,
        "gross_sales": recognized_totals["gross"],
        "refunds": recognized_totals["refunds"],
        "net_sales": net_sales,
        "cogs": net_cogs,
        "gross_profit": net_sales - net_cogs,
        "average_order_value": net_sales / recognized_count if recognized_count else 0,
        "paid_sales": paid_sales,
        "pending_payments": orders.filter(payment_status=Order.PaymentStatus.PENDING).count(),
        "low_stock": Product.objects.filter(
            is_active=True,
            stock_quantity__gt=F("reserved_quantity"),
            stock_quantity__lte=F("reserved_quantity") + 5,
        ).count(),
        "out_of_stock": Product.objects.filter(is_active=True, stock_quantity__lte=F("reserved_quantity")).count(),
        "expired_batches": InventoryBatch.objects.filter(
            is_active=True, expiry_date__lt=today, quantity__gt=0,
        ).count(),
        "expiring_batches": InventoryBatch.objects.filter(
            is_active=True, expiry_date__gte=today,
            expiry_date__lte=today + timedelta(days=90), quantity__gt=0,
        ).count(),
        "customers": get_user_model().objects.filter(is_staff=False).count(),
        "latest_orders": orders.select_related("governorate")[:8],
        "can_view_orders": can_view_orders,
        "can_view_financial": can_view_financial,
        "can_view_inventory": can_view_inventory,
        "can_view_customers": can_view_customers,
    }
    return render(request, "dashboard/home.html", context)


@dashboard_permission("products.view_product")
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


@dashboard_permission("products.view_product")
def product_form(request, pk=None):
    required = "products.change_product" if pk else "products.add_product"
    if not request.user.is_superuser and not request.user.has_perm(required):
        raise PermissionDenied
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


@dashboard_permission("products.delete_product")
@require_POST
def product_delete(request, pk):
    product = get_object_or_404(Product, pk=pk)
    try:
        product.delete()
    except ProtectedError:
        # Inventory batches and reservations are audit records and must not be
        # cascaded away.  Archive the product so it disappears from the public
        # catalog while keeping historical stock/order data intact.
        product.is_active = False
        product.save(update_fields=["is_active", "updated_at"])
        messages.warning(
            request,
            "لا يمكن حذف المنتج نهائيًا لارتباطه بسجل مخزون أو طلبات؛ "
            "تم إيقافه وإخفاؤه من المتجر بدلًا من ذلك.",
        )
    else:
        messages.success(request, "تم حذف المنتج نهائيًا.")
    return redirect("dashboard:products")


@dashboard_permission("products.change_product")
@require_POST
def product_toggle(request, pk):
    product = get_object_or_404(Product, pk=pk)
    product.is_active = not product.is_active
    product.save(update_fields=["is_active", "updated_at"])
    messages.success(request, "تم تحديث حالة المنتج.")
    return redirect("dashboard:products")


@dashboard_permission("products.view_product", "products.view_inventorybatch")
def inventory(request):
    products = Product.objects.select_related("category").order_by("stock_quantity", "name")
    return render(request, "dashboard/inventory.html", {
        "page_obj": paginate(request, products),
        "expiring_batches": InventoryBatch.objects.filter(
            is_active=True,
            expiry_date__isnull=False,
            expiry_date__lte=timezone.localdate() + timedelta(days=90),
        ).select_related("product", "variant")[:10],
    })


@dashboard_permission("products.view_productvariant")
def variant_list(request, product_pk):
    product = get_object_or_404(Product, pk=product_pk)
    return render(request, "dashboard/variants.html", {
        "product": product,
        "variants": product.variants.prefetch_related("options"),
    })


@dashboard_permission("products.view_productvariant")
def variant_form(request, product_pk, pk=None):
    product = get_object_or_404(Product, pk=product_pk)
    instance = get_object_or_404(ProductVariant, pk=pk, product=product) if pk else None
    required = "products.change_productvariant" if instance else "products.add_productvariant"
    if not request.user.is_superuser and not request.user.has_perm(required):
        raise PermissionDenied
    form = ProductVariantForm(request.POST or None, instance=instance)
    if request.method == "POST" and form.is_valid():
        variant = form.save(commit=False)
        variant.product = product
        variant.save()
        form.save_m2m()
        if not product.has_variants:
            Product.objects.filter(pk=product.pk).update(has_variants=True)
        messages.success(request, "تم حفظ خيار المنتج.")
        return redirect("dashboard:variants", product_pk=product.pk)
    return render(request, "dashboard/form.html", {"form": form, "title": "خيار منتج"})


@dashboard_permission("products.view_variantoption")
def variant_option_list(request):
    return render(request, "dashboard/variant_options.html", {"options": VariantOption.objects.all()})


@dashboard_permission("products.view_variantoption")
def variant_option_form(request, pk=None):
    instance = get_object_or_404(VariantOption, pk=pk) if pk else None
    required = "products.change_variantoption" if instance else "products.add_variantoption"
    if not request.user.is_superuser and not request.user.has_perm(required):
        raise PermissionDenied
    return _model_form(request, VariantOptionForm, "dashboard:variant_options", "قيمة خيار", instance)


@dashboard_permission("products.view_inventorybatch")
def batch_list(request):
    batches = InventoryBatch.objects.select_related("product", "variant")
    query = request.GET.get("q", "").strip()
    if query:
        batches = batches.filter(Q(batch_number__icontains=query) | Q(product__name__icontains=query))
    return render(request, "dashboard/batches.html", {"page_obj": paginate(request, batches)})


@dashboard_permission("products.view_inventorybatch")
def batch_form(request, pk=None):
    instance = get_object_or_404(InventoryBatch, pk=pk) if pk else None
    required = "products.change_inventorybatch" if instance else "products.add_inventorybatch"
    if not request.user.is_superuser and not request.user.has_perm(required):
        raise PermissionDenied
    old_quantity = instance.quantity if instance else 0
    form = InventoryBatchForm(request.POST or None, instance=instance)
    if instance:
        form.fields["product"].disabled = True
        form.fields["variant"].disabled = True
    if request.method == "POST" and form.is_valid():
        with transaction.atomic():
            batch = form.save()
            delta = batch.quantity - old_quantity
            if delta:
                target_model = ProductVariant if batch.variant_id else Product
                target_id = batch.variant_id or batch.product_id
                updated = target_model.objects.filter(
                    pk=target_id,
                    stock_quantity__gte=F("reserved_quantity") - delta,
                ).update(stock_quantity=F("stock_quantity") + delta)
                if not updated:
                    raise ValueError("لا يمكن خفض التشغيلة لأقل من الكمية المحجوزة.")
        messages.success(request, "تم حفظ تشغيلة المخزون.")
        return redirect("dashboard:batches")
    return render(request, "dashboard/form.html", {"form": form, "title": "تشغيلة مخزون"})


@dashboard_permission("products.view_category")
def category_list(request):
    return render(request, "dashboard/categories.html", {"categories": Category.objects.all()})


@dashboard_permission("products.view_category")
def category_form(request, pk=None):
    required = "products.change_category" if pk else "products.add_category"
    if not request.user.is_superuser and not request.user.has_perm(required):
        raise PermissionDenied
    instance = get_object_or_404(Category, pk=pk) if pk else None
    form = CategoryForm(request.POST or None, request.FILES or None, instance=instance)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "تم حفظ التصنيف.")
        return redirect("dashboard:categories")
    return render(request, "dashboard/form.html", {"form": form, "title": "تعديل تصنيف" if instance else "إضافة تصنيف"})


@dashboard_permission("products.delete_category")
@require_POST
def category_delete(request, pk):
    category = get_object_or_404(Category, pk=pk)
    if category.products.exists():
        messages.error(request, "لا يمكن حذف تصنيف يحتوي على منتجات.")
    else:
        category.delete()
        messages.success(request, "تم حذف التصنيف.")
    return redirect("dashboard:categories")


@dashboard_permission("orders.view_order")
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


@dashboard_permission("orders.view_order")
def order_detail(request, pk):
    order = get_object_or_404(Order.objects.select_related("governorate", "user").prefetch_related("items"), pk=pk)
    original_status = order.status
    form = OrderUpdateForm(request.POST or None, instance=order, user=request.user)
    if request.method == "POST" and form.is_valid():
        if not request.user.is_superuser and not (
            request.user.has_perm("orders.transition_order")
            or request.user.has_perm("orders.verify_payment")
        ):
            raise PermissionDenied
        new_status = form.cleaned_data["status"]
        try:
            order = transition_order(
                order,
                new_status=new_status,
                payment_status=form.cleaned_data["payment_status"],
                payment_note=form.cleaned_data["payment_note"],
                actor=request.user,
                ip_address=request.META.get("REMOTE_ADDR"),
            )
        except OrderTransitionError as exc:
            messages.error(request, str(exc))
            return redirect("dashboard:order_detail", pk=order.pk)
        messages.success(request, "تم تحديث الطلب.")
        return redirect("dashboard:order_detail", pk=order.pk)
    return render(request, "dashboard/order_detail.html", {"order": order, "form": form})


@dashboard_permission("orders.view_payment_receipt")
@rate_limit("private-payment-receipt", limit=30, window=60, methods=("GET",))
def payment_receipt(request, pk):
    order = get_object_or_404(Order, pk=pk)
    if not order.payment_receipt:
        raise Http404
    content_type = mimetypes.guess_type(order.payment_receipt.name)[0] or "application/octet-stream"
    suffix = Path(order.payment_receipt.name).suffix.lower()
    return FileResponse(
        order.payment_receipt.open("rb"),
        content_type=content_type,
        as_attachment=False,
        filename=f"{order.order_number}-receipt{suffix}",
    )


@dashboard_permission("orders.view_order")
def payments(request):
    orders = Order.objects.filter(payment_method=Order.PaymentMethod.INSTAPAY).select_related("governorate")
    status = request.GET.get("status")
    if status:
        orders = orders.filter(payment_status=status)
    return render(request, "dashboard/payments.html", {
        "page_obj": paginate(request, orders), "payment_statuses": Order.PaymentStatus.choices,
    })


@dashboard_permission("orders.view_returnrequest")
def return_list(request):
    returns = ReturnRequest.objects.select_related("order", "user")
    status = request.GET.get("status", "")
    if status:
        returns = returns.filter(status=status)
    return render(request, "dashboard/returns.html", {
        "page_obj": paginate(request, returns),
        "return_statuses": ReturnRequest.Status.choices,
    })


@dashboard_permission("orders.view_returnrequest", "orders.change_returnrequest")
def return_detail(request, pk):
    return_request = get_object_or_404(
        ReturnRequest.objects.select_related("order", "user").prefetch_related("items__order_item"),
        pk=pk,
    )
    form = ReturnUpdateForm(request.POST or None, instance=return_request)
    if request.method == "POST" and form.is_valid():
        restockable = {
            item.pk: form.cleaned_data.get(f"restockable_{item.pk}", False)
            for item in return_request.items.all()
        }
        try:
            process_return(
                return_request,
                new_status=form.cleaned_data["status"],
                refund_amount=form.cleaned_data["refund_amount"],
                admin_note=form.cleaned_data["admin_note"],
                restockable=restockable,
                actor=request.user,
            )
        except OrderTransitionError as exc:
            messages.error(request, str(exc))
        else:
            messages.success(request, "تم تحديث طلب الإرجاع.")
            return redirect("dashboard:return_detail", pk=return_request.pk)
    return render(request, "dashboard/return_detail.html", {
        "return_request": return_request,
        "form": form,
    })


@dashboard_permission("auth.view_user")
def user_list(request):
    users = get_user_model().objects.annotate(order_count=Count("orders")).order_by("-date_joined")
    query = request.GET.get("q", "").strip()
    if query:
        users = users.filter(Q(username__icontains=query) | Q(first_name__icontains=query) | Q(email__icontains=query))
    return render(request, "dashboard/users.html", {"page_obj": paginate(request, users)})


@dashboard_permission("auth.view_user")
def user_detail(request, pk):
    user = get_object_or_404(get_user_model(), pk=pk)
    role_form = UserRoleForm(request.POST or None, instance=user) if request.user.is_superuser else None
    if request.method == "POST":
        if not request.user.is_superuser:
            raise PermissionDenied
        if role_form.is_valid():
            if user == request.user and not role_form.cleaned_data["is_staff"]:
                role_form.add_error("is_staff", "لا يمكنك إزالة وصولك الإداري أثناء الجلسة.")
            else:
                role_form.save()
                messages.success(request, "تم تحديث دور المستخدم.")
                return redirect("dashboard:user_detail", pk=user.pk)
    return render(request, "dashboard/user_detail.html", {
        "customer": user,
        "orders": user.orders.all()[:20],
        "role_form": role_form,
    })


@dashboard_permission("auth.change_user")
@require_POST
def user_toggle(request, pk):
    user = get_object_or_404(get_user_model(), pk=pk)
    if user == request.user:
        messages.error(request, "لا يمكنك تعطيل حسابك الحالي.")
    elif user.is_staff and not request.user.is_superuser:
        raise PermissionDenied
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


@dashboard_permission("orders.view_shippingzone")
def shipping_list(request):
    return _model_list(request, ShippingZone, "dashboard/simple_list.html", "objects")


@dashboard_permission("orders.view_shippingzone")
def shipping_form(request, pk=None):
    required = "orders.change_shippingzone" if pk else "orders.add_shippingzone"
    if not request.user.is_superuser and not request.user.has_perm(required):
        raise PermissionDenied
    instance = get_object_or_404(ShippingZone, pk=pk) if pk else None
    return _model_form(request, ShippingZoneForm, "dashboard:shipping", "منطقة شحن", instance)


@dashboard_permission("orders.view_coupon")
def coupon_list(request):
    return render(request, "dashboard/coupons.html", {"coupons": Coupon.objects.all()})


@dashboard_permission("orders.view_coupon")
def coupon_form(request, pk=None):
    required = "orders.change_coupon" if pk else "orders.add_coupon"
    if not request.user.is_superuser and not request.user.has_perm(required):
        raise PermissionDenied
    instance = get_object_or_404(Coupon, pk=pk) if pk else None
    return _model_form(request, CouponForm, "dashboard:coupons", "كوبون خصم", instance)


@dashboard_permission("core.view_banner")
def banner_list(request):
    return render(request, "dashboard/banners.html", {"banners": Banner.objects.all()})


@dashboard_permission("core.view_banner")
def banner_form(request, pk=None):
    required = "core.change_banner" if pk else "core.add_banner"
    if not request.user.is_superuser and not request.user.has_perm(required):
        raise PermissionDenied
    instance = get_object_or_404(Banner, pk=pk) if pk else None
    return _model_form(request, BannerForm, "dashboard:banners", "بانر", instance)


@dashboard_permission("core.view_offer")
def offer_list(request):
    offers = Offer.objects.prefetch_related("products")
    return render(request, "dashboard/offers.html", {"offers": offers})


@dashboard_permission("core.view_offer")
def offer_form(request, pk=None):
    required = "core.change_offer" if pk else "core.add_offer"
    if not request.user.is_superuser and not request.user.has_perm(required):
        raise PermissionDenied
    instance = get_object_or_404(Offer, pk=pk) if pk else None
    title = "تعديل العرض" if instance else "إضافة عرض"
    return _model_form(request, OfferForm, "dashboard:offers", title, instance)


@dashboard_permission("core.view_contentpage")
def page_list(request):
    return render(request, "dashboard/pages.html", {"pages": ContentPage.objects.all()})


@dashboard_permission("core.view_contentpage")
def page_form(request, pk=None):
    required = "core.change_contentpage" if pk else "core.add_contentpage"
    if not request.user.is_superuser and not request.user.has_perm(required):
        raise PermissionDenied
    instance = get_object_or_404(ContentPage, pk=pk) if pk else None
    return _model_form(request, ContentPageForm, "dashboard:pages", "صفحة محتوى", instance)


@dashboard_permission("core.view_socialgalleryimage")
def gallery_list(request):
    return render(request, "dashboard/gallery.html", {"gallery_items": SocialGalleryImage.objects.all()})


@dashboard_permission("core.view_socialgalleryimage")
def gallery_form(request, pk=None):
    required = "core.change_socialgalleryimage" if pk else "core.add_socialgalleryimage"
    if not request.user.is_superuser and not request.user.has_perm(required):
        raise PermissionDenied
    instance = get_object_or_404(SocialGalleryImage, pk=pk) if pk else None
    return _model_form(request, SocialGalleryForm, "dashboard:gallery", "صورة المعرض", instance)


@dashboard_permission("core.view_routinestep")
def routine_list(request):
    return render(request, "dashboard/routine.html", {"routine_steps": RoutineStep.objects.select_related("category", "product")})


@dashboard_permission("core.view_routinestep")
def routine_form(request, pk=None):
    required = "core.change_routinestep" if pk else "core.add_routinestep"
    if not request.user.is_superuser and not request.user.has_perm(required):
        raise PermissionDenied
    instance = get_object_or_404(RoutineStep, pk=pk) if pk else None
    return _model_form(request, RoutineStepForm, "dashboard:routine", "خطوة روتين", instance)


@dashboard_permission("core.change_storesettings")
def settings_edit(request):
    settings = StoreSettings.load()
    form = StoreSettingsForm(request.POST or None, request.FILES or None, instance=settings)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "تم حفظ إعدادات المتجر.")
        return redirect("dashboard:settings")
    return render(request, "dashboard/form.html", {"form": form, "title": "إعدادات المتجر"})


@dashboard_permission("core.view_contactmessage")
def messages_list(request):
    return render(request, "dashboard/messages.html", {"contact_messages": ContactMessage.objects.all()})


@dashboard_permission("core.view_contactmessage", "core.change_contactmessage")
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
        "shipping": (ShippingZone, "dashboard:shipping", "orders.delete_shippingzone"),
        "coupon": (Coupon, "dashboard:coupons", "orders.delete_coupon"),
        "banner": (Banner, "dashboard:banners", "core.delete_banner"),
        "offer": (Offer, "dashboard:offers", "core.delete_offer"),
        "page": (ContentPage, "dashboard:pages", "core.delete_contentpage"),
        "gallery": (SocialGalleryImage, "dashboard:gallery", "core.delete_socialgalleryimage"),
        "routine": (RoutineStep, "dashboard:routine", "core.delete_routinestep"),
    }
    if model_name not in models:
        return HttpResponseNotAllowed(["POST"])
    model, redirect_name, permission = models[model_name]
    if not request.user.is_superuser and not request.user.has_perm(permission):
        raise PermissionDenied
    try:
        get_object_or_404(model, pk=pk).delete()
    except ProtectedError:
        messages.error(request, "لا يمكن حذف هذا العنصر لأنه مرتبط بطلبات أو بيانات أخرى.")
    else:
        messages.success(request, "تم الحذف بنجاح.")
    return redirect(redirect_name)
