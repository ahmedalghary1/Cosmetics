from urllib.parse import quote

from cart.cart import Cart

from .models import ContentPage, StoreSettings


def store_context(request):
    settings = StoreSettings.load()
    whatsapp_url = ""
    if settings.whatsapp_enabled and settings.whatsapp:
        number = "".join(character for character in settings.whatsapp if character.isdigit())
        whatsapp_url = f"https://wa.me/{number}?text={quote(settings.whatsapp_message)}"
    wishlist_product_ids = set()
    if request.user.is_authenticated:
        wishlist_product_ids = set(request.user.wishlist_items.values_list("product_id", flat=True))
    return {
        "store_settings": settings,
        "cart_count": len(Cart(request)),
        "footer_pages": ContentPage.objects.filter(is_active=True)[:8],
        "whatsapp_url": whatsapp_url,
        "wishlist_product_ids": wishlist_product_ids,
    }
