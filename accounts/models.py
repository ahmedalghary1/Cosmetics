from django.conf import settings
from django.db import models

from core.models import TimeStampedModel


class Profile(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, related_name="profile", on_delete=models.CASCADE)
    phone = models.CharField("رقم الهاتف", max_length=30, blank=True)

    class Meta:
        verbose_name = "ملف عميل"
        verbose_name_plural = "ملفات العملاء"

    def __str__(self):
        return self.user.get_full_name() or self.user.username


class WishlistItem(TimeStampedModel):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, related_name="wishlist_items", on_delete=models.CASCADE)
    product = models.ForeignKey("products.Product", related_name="wishlisted_by", on_delete=models.CASCADE)

    class Meta:
        verbose_name = "عنصر مفضلة"
        verbose_name_plural = "المفضلة"
        constraints = [models.UniqueConstraint(fields=["user", "product"], name="unique_user_product_wishlist")]

    def __str__(self):
        return f"{self.user} - {self.product}"
