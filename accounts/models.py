from django.conf import settings
from django.db import models

from core.models import TimeStampedModel


def normalize_phone(value):
    digits = "".join(character for character in (value or "") if character.isdigit())
    if digits.startswith("20") and len(digits) == 12:
        digits = f"0{digits[2:]}"
    return digits


class Profile(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, related_name="profile", on_delete=models.CASCADE)
    phone = models.CharField("رقم الهاتف", max_length=30, blank=True)
    normalized_phone = models.CharField(
        "رقم الهاتف الموحد", max_length=20,
        unique=True, null=True, blank=True, editable=False,
    )

    class Meta:
        verbose_name = "ملف عميل"
        verbose_name_plural = "ملفات العملاء"
        permissions = [("export_customer_data", "Can export customer data")]

    def __str__(self):
        return self.user.get_full_name() or self.user.username

    def save(self, *args, **kwargs):
        self.normalized_phone = normalize_phone(self.phone) or None
        super().save(*args, **kwargs)


class WishlistItem(TimeStampedModel):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, related_name="wishlist_items", on_delete=models.CASCADE)
    product = models.ForeignKey("products.Product", related_name="wishlisted_by", on_delete=models.CASCADE)

    class Meta:
        verbose_name = "عنصر مفضلة"
        verbose_name_plural = "المفضلة"
        constraints = [models.UniqueConstraint(fields=["user", "product"], name="unique_user_product_wishlist")]

    def __str__(self):
        return f"{self.user} - {self.product}"
