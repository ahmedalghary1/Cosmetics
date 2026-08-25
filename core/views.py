from django.contrib import messages
from django.db.models import Q
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.html import escape

from products.models import Category, Product
from .rate_limit import rate_limit

from .forms import ContactForm
from .models import Banner, ContentPage, Offer, RoutineStep, SocialGalleryImage


def home(request):
    products = Product.objects.active().select_related("category")
    offer = Offer.objects.current().first()
    if offer and offer.sell_as_bundle and offer.bundle_product_id:
        offer_products = products.filter(pk=offer.bundle_product_id)
    elif offer:
        offer_products = offer.products.active().select_related("category")[:5]
    else:
        offer_products = Product.objects.none()
    context = {
        "hero": Banner.objects.filter(position=Banner.Position.HERO, is_active=True).first(),
        "promo": Banner.objects.filter(position=Banner.Position.PROMO, is_active=True).first(),
        "categories": Category.objects.filter(is_active=True)[:8],
        "best_sellers": products.filter(is_best_seller=True)[:5],
        "new_products": products.filter(is_new=True).order_by("-created_at")[:5],
        "offer": offer,
        "offer_products": offer_products,
        "routine_steps": RoutineStep.objects.filter(is_active=True).select_related("category", "product")[:4],
        "gallery": SocialGalleryImage.objects.filter(is_active=True)[:6],
    }
    return render(request, "core/home.html", context)


def content_page(request, slug):
    if slug == "من-نحن":
        return redirect("core:about", permanent=True)
    page = get_object_or_404(ContentPage, slug=slug, is_active=True)
    return render(request, "core/page.html", {"page": page})


def about(request):
    page = get_object_or_404(ContentPage, slug="من-نحن", is_active=True)
    return render(request, "core/about.html", {"page": page})


@rate_limit("contact", limit=5, window=600)
def contact(request):
    form = ContactForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "تم إرسال رسالتك بنجاح، وسنتواصل معك قريبًا.")
        return redirect("core:contact")
    return render(request, "core/contact.html", {"form": form})


def search(request):
    query = request.GET.get("q", "").strip()
    products = Product.objects.active().select_related("category")
    if query:
        products = products.filter(
            Q(name__icontains=query)
            | Q(short_description__icontains=query)
            | Q(description__icontains=query)
            | Q(category__name__icontains=query)
        ).distinct()
    else:
        products = products.none()
    return render(request, "products/search.html", {"products": products[:24], "query": query})


def robots_txt(request):
    sitemap_url = request.build_absolute_uri("/sitemap.xml")
    return HttpResponse(
        f"User-agent: *\nAllow: /\nDisallow: /dashboard/\nDisallow: /developer-admin/\nSitemap: {sitemap_url}\n",
        content_type="text/plain; charset=utf-8",
    )


def sitemap_xml(request):
    urls = [request.build_absolute_uri("/")]
    urls.extend(request.build_absolute_uri(product.get_absolute_url()) for product in Product.objects.active())
    urls.extend(
        request.build_absolute_uri(category.get_absolute_url())
        for category in Category.objects.filter(is_active=True)
    )
    urls.extend(
        request.build_absolute_uri(page.get_absolute_url())
        for page in ContentPage.objects.filter(is_active=True)
    )
    entries = "".join(f"<url><loc>{escape(url)}</loc></url>" for url in urls)
    body = f'<?xml version="1.0" encoding="UTF-8"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">{entries}</urlset>'
    return HttpResponse(body, content_type="application/xml; charset=utf-8")


def error_404(request, exception):
    return render(request, "404.html", status=404)


def error_500(request):
    return render(request, "500.html", status=500)
