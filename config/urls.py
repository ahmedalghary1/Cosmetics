from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path

handler404 = "core.views.error_404"
handler500 = "core.views.error_500"

urlpatterns = [
    path("developer-admin/", admin.site.urls),
    path("", include("core.urls")),
    path("products/", include("products.urls")),
    path("category/", include("products.category_urls")),
    path("cart/", include("cart.urls")),
    path("checkout/", include("orders.urls")),
    path("account/", include("accounts.urls")),
    path("dashboard/", include("dashboard.urls")),
]

if settings.DEBUG or getattr(settings, "SERVE_MEDIA_FILES", False):
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
