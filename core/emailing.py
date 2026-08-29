import logging

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string

from .models import StoreSettings


logger = logging.getLogger(__name__)


def admin_notification_recipients():
    """Return configured store/admin addresses without sending duplicates."""
    store = StoreSettings.load()
    return list(dict.fromkeys(
        address for address in (store.email, settings.EMAIL_HOST_USER) if address
    ))


def send_templated_email(
    *, subject, recipients, title, message, details=None, reply_to=None, fail_silently=False,
    action_url="", action_label="",
):
    recipients = [address for address in recipients if address]
    if not recipients:
        return 0
    store = StoreSettings.load()
    context = {
        "store_name": store.store_name,
        "store_email": store.email or settings.EMAIL_HOST_USER,
        "title": title,
        "message": message,
        "details": details or [],
        "action_url": action_url,
        "action_label": action_label,
    }
    email = EmailMultiAlternatives(
        subject=subject,
        body=render_to_string("emails/notification.txt", context),
        from_email=settings.DEFAULT_FROM_EMAIL,
        to=recipients,
        reply_to=reply_to or None,
    )
    email.attach_alternative(render_to_string("emails/notification.html", context), "text/html")
    try:
        return email.send(fail_silently=False)
    except Exception:
        logger.exception("Email delivery failed for subject %s", subject)
        if fail_silently:
            return 0
        raise
