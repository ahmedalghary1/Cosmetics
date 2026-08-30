from django import forms
from django.contrib import messages
from django.core.paginator import Paginator
from django.db.models import F, IntegerField, OuterRef, Q, Subquery, Value
from django.db.models.functions import Coalesce
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from core.models import Offer
from core.rate_limit import rate_limit

from .forms import ProductFilterForm
from .models import BackInStockSubscription, Category, Product, ProductCategoryOrder


SORT_OPTIONS = {
    "newest": "-created_at",
    "price_asc": "price",
    "price_desc": "-price",
    "best": "-sales_count",
}


def product_list(request, category_slug=None):
    products = Product.objects.active().select_related("category").prefetch_related("categories")
    selected_category = None
    ordering_category = None
    selected_offer = None
    filter_form = ProductFilterForm(request.GET or None)
    filters = filter_form.cleaned_data if filter_form.is_valid() else {}
    if category_slug:
        selected_category = get_object_or_404(Category, slug=category_slug, is_active=True)
        ordering_category = selected_category
        products = products.filter(categories=selected_category).distinct()

    query = filters.get("q", "").strip()
    if query:
        products = products.filter(
            Q(name__icontains=query)
            | Q(description__icontains=query)
            | Q(categories__name__icontains=query)
        ).distinct()
    category_filter = filters.get("category", "").strip()
    if category_filter and not selected_category:
        ordering_category = Category.objects.filter(slug=category_filter, is_active=True).first()
        products = products.filter(categories=ordering_category).distinct()
    if filters.get("min_price") is not None:
        products = products.filter(price__gte=filters["min_price"])
    if filters.get("max_price") is not None:
        products = products.filter(price__lte=filters["max_price"])
    if filters.get("in_stock"):
        bundle_ids = [
            product.pk
            for product in products.filter(is_bundle=True).prefetch_related(
                "bundle_items__product", "bundle_items__variant",
            )
            if product.in_stock
        ]
        products = products.filter(
            Q(pk__in=bundle_ids)
            | Q(is_bundle=False, has_variants=False, stock_quantity__gt=F("reserved_quantity"))
            | Q(is_bundle=False, has_variants=True, variants__is_active=True, variants__stock_quantity__gt=F("variants__reserved_quantity"))
        ).distinct()
    if filters.get("offers"):
        products = products.filter(old_price__isnull=False)
    offer_id = request.GET.get("offer", "").strip()
    if offer_id.isdigit():
        selected_offer = Offer.objects.current().filter(pk=offer_id).first()
        if selected_offer:
            products = products.filter(offer_campaigns=selected_offer)
        else:
            products = products.none()
    if filters.get("best"):
        products = products.filter(is_best_seller=True)
    if filters.get("new"):
        products = products.filter(is_new=True)

    sort = filters.get("sort") or ("recommended" if ordering_category else "newest")
    if sort == "recommended" and not ordering_category:
        sort = "newest"
    if sort == "recommended" and ordering_category:
        saved_order = ProductCategoryOrder.objects.filter(
            category=ordering_category,
            product_id=OuterRef("pk"),
        ).values("order")[:1]
        products = products.annotate(
            category_order=Coalesce(
                Subquery(saved_order, output_field=IntegerField()),
                Value(2147483647),
            ),
        ).order_by("category_order", "-created_at", "pk")
    else:
        products = products.order_by(SORT_OPTIONS.get(sort, "-created_at"))
    paginator = Paginator(products, 12)
    page = paginator.get_page(request.GET.get("page"))
    query_params = request.GET.copy()
    query_params.pop("page", None)
    context = {
        "page_obj": page,
        "categories": Category.objects.filter(is_active=True),
        "selected_category": selected_category,
        "ordering_category": ordering_category,
        "selected_offer": selected_offer,
        "sort": sort,
        "query_string": query_params.urlencode(),
        "filter_form": filter_form,
    }
    return render(request, "products/list.html", context)


def product_detail(request, slug):
    product = get_object_or_404(
        Product.objects.active().select_related("category").prefetch_related(
            "categories", "images", "variants", "bundle_items__product", "bundle_items__variant",
        ), slug=slug
    )
    related = (
        Product.objects.active()
        .filter(categories__in=product.categories.all())
        .exclude(pk=product.pk)
        .select_related("category").prefetch_related("categories").distinct()[:4]
    )
    analytics_product = {
        "currency": "EGP",
        "value": float(product.price),
        "items": [{"item_id": product.sku, "item_name": product.name, "price": float(product.price)}],
    }
    return render(request, "products/detail.html", {
        "product": product, "related_products": related,
        "analytics_product": analytics_product,
    })


@require_POST
@rate_limit("back-in-stock", limit=5, window=3600)
def subscribe_back_in_stock(request, product_id):
    product = get_object_or_404(Product.objects.active(), pk=product_id)
    if product.in_stock:
        messages.info(request, "المنتج متوفر الآن ويمكنك إضافته إلى السلة.")
        return redirect(product.get_absolute_url())

    email_field = forms.EmailField()
    try:
        email = email_field.clean(request.POST.get("email", "")).lower()
    except forms.ValidationError:
        messages.error(request, "أدخلي بريدًا إلكترونيًا صحيحًا لاستلام التنبيه.")
        return redirect(product.get_absolute_url())

    product_url = request.build_absolute_uri(product.get_absolute_url())
    subscription, created = BackInStockSubscription.objects.update_or_create(
        product=product,
        email=email,
        defaults={"is_active": True, "notified_at": None, "product_url": product_url},
    )
    if created:
        messages.success(request, "تم تسجيل بريدك وسنخبرك فور عودة المنتج للمخزون.")
    else:
        messages.success(request, "تم تجديد تنبيه عودة المنتج لهذا البريد.")
    return redirect(product.get_absolute_url())
