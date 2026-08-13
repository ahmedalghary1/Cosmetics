from django.core.paginator import Paginator
from django.db.models import Q
from django.shortcuts import get_object_or_404, render

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
    if category_slug:
        selected_category = get_object_or_404(Category, slug=category_slug, is_active=True)
        products = products.filter(category=selected_category)

    query = request.GET.get("q", "").strip()
    if query:
        products = products.filter(
            Q(name__icontains=query)
            | Q(description__icontains=query)
            | Q(category__name__icontains=query)
        ).distinct()
    category_filter = request.GET.get("category", "").strip()
    if category_filter and not selected_category:
        products = products.filter(category__slug=category_filter)
    if request.GET.get("min_price"):
        products = products.filter(price__gte=request.GET["min_price"])
    if request.GET.get("max_price"):
        products = products.filter(price__lte=request.GET["max_price"])
    if request.GET.get("in_stock"):
        products = products.filter(stock_quantity__gt=0)
    if request.GET.get("offers"):
        products = products.filter(old_price__isnull=False)
    if request.GET.get("best"):
        products = products.filter(is_best_seller=True)
    if request.GET.get("new"):
        products = products.filter(is_new=True)

    sort = request.GET.get("sort", "newest")
    products = products.order_by(SORT_OPTIONS.get(sort, "-created_at"))
    paginator = Paginator(products, 12)
    page = paginator.get_page(request.GET.get("page"))
    query_params = request.GET.copy()
    query_params.pop("page", None)
    context = {
        "page_obj": page,
        "categories": Category.objects.filter(is_active=True),
        "selected_category": selected_category,
        "sort": sort,
        "query_string": query_params.urlencode(),
    }
    return render(request, "products/list.html", context)


def product_detail(request, slug):
    product = get_object_or_404(
        Product.objects.active().select_related("category").prefetch_related("images"), slug=slug
    )
    related = (
        Product.objects.active()
        .filter(category=product.category)
        .exclude(pk=product.pk)
        .select_related("category")[:4]
    )
    return render(request, "products/detail.html", {"product": product, "related_products": related})
