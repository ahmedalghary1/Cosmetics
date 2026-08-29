import logging

from django.db import transaction
from django.utils import timezone

from core.emailing import send_templated_email
from core.models import StoreSettings

from .models import BackInStockSubscription, Product


logger = logging.getLogger(__name__)


def notify_back_in_stock(product_id):
    """Notify each active subscriber once when a public product is available."""
    store = StoreSettings.load()
    if not store.back_in_stock_emails_enabled:
        return 0
    try:
        product = Product.objects.get(pk=product_id, is_active=True)
    except Product.DoesNotExist:
        return 0
    if not product.in_stock:
        return 0

    sent = 0
    subscriptions = BackInStockSubscription.objects.filter(
        product=product, is_active=True,
    )
    for subscription in subscriptions.iterator():
        try:
            delivered = send_templated_email(
                subject=f"عاد للمخزون — {product.name}",
                recipients=[subscription.email],
                title="المنتج متوفر الآن",
                message=f"المنتج «{product.name}» الذي طلبتِ متابعته عاد للمخزون.",
                details=[("المنتج", product.name), ("السعر", f"{product.price} {store.currency}")],
                action_url=subscription.product_url,
                action_label="عرض المنتج",
            )
        except Exception:
            logger.exception("Back-in-stock email failed for product %s", product_id)
            continue
        if delivered:
            BackInStockSubscription.objects.filter(pk=subscription.pk, is_active=True).update(
                is_active=False, notified_at=timezone.now(),
            )
            sent += 1
    return sent


def notify_back_in_stock_after_commit(*product_ids):
    for product_id in set(filter(None, product_ids)):
        transaction.on_commit(lambda product_id=product_id: notify_back_in_stock(product_id))
