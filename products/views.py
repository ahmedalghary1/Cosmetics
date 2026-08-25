from django.core.paginator import Paginator
from django.db.models import F, Q
from django.shortcuts import get_object_or_404, render

from core.models import Offer

from .forms import ProductFilterForm
from .models import Category, Product


SORT_OPTIONS = {
    "newest": "-created_at",
    "price_asc": "price",
    "price_desc": "-price",
    "best": "-sales_count",
}


def product_list(request, category_slug=None):
    products = Product.objects.active().select_related("category")
    selected_category = None
    selected_offer = None
    filter_form = ProductFilterForm(request.GET or None)
    filters = filter_form.cleaned_data if filter_form.is_valid() else {}
    if category_slug:
        selected_category = get_object_or_404(Category, slug=category_slug, is_active=True)
        products = products.filter(category=selected_category)

    query = filters.get("q", "").strip()
    if query:
        products = products.filter(
            Q(name__icontains=query)
            | Q(description__icontains=query)
            | Q(category__name__icontains=query)
        ).distinct()
    category_filter = filters.get("category", "").strip()
    if category_filter and not selected_category:
        products = products.filter(category__slug=category_filter)
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

    sort = filters.get("sort") or "newest"
    products = products.order_by(SORT_OPTIONS.get(sort, "-created_at"))
    paginator = Paginator(products, 12)
    page = paginator.get_page(request.GET.get("page"))
    query_params = request.GET.copy()
    query_params.pop("page", None)
    context = {
        "page_obj": page,
        "categories": Category.objects.filter(is_active=True),
        "selected_category": selected_category,
        "selected_offer": selected_offer,
        "sort": sort,
        "query_string": query_params.urlencode(),
        "filter_form": filter_form,
    }
    return render(request, "products/list.html", context)


def product_detail(request, slug):
    product = get_object_or_404(
        Product.objects.active().select_related("category").prefetch_related(
            "images", "variants", "bundle_items__product", "bundle_items__variant",
        ), slug=slug
    )
    related = (
        Product.objects.active()
        .filter(category=product.category)
        .exclude(pk=product.pk)
        .select_related("category")[:4]
    )
    return render(request, "products/detail.html", {"product": product, "related_products": related})
