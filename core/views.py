from django.contrib import messages
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render

from products.models import Category, Product

from .forms import ContactForm
from .models import Banner, ContentPage, RoutineStep, SocialGalleryImage


def home(request):
    products = Product.objects.active().select_related("category")
    context = {
        "hero": Banner.objects.filter(position=Banner.Position.HERO, is_active=True).first(),
        "promo": Banner.objects.filter(position=Banner.Position.PROMO, is_active=True).first(),
        "categories": Category.objects.filter(is_active=True)[:8],
        "best_sellers": products.filter(is_best_seller=True)[:5],
        "new_products": products.filter(is_new=True).order_by("-created_at")[:5],
        "offers": products.filter(old_price__isnull=False).order_by("-created_at")[:5],
        "routine_steps": RoutineStep.objects.filter(is_active=True).select_related("category", "product")[:4],
        "gallery": SocialGalleryImage.objects.filter(is_active=True)[:6],
    }
    return render(request, "core/home.html", context)


def content_page(request, slug):
    page = get_object_or_404(ContentPage, slug=slug, is_active=True)
    return render(request, "core/page.html", {"page": page})


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


def error_404(request, exception):
    return render(request, "404.html", status=404)


def error_500(request):
    return render(request, "500.html", status=500)
