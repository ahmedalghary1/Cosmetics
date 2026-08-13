from django.db import models
from django.urls import reverse

from .validators import validate_image_upload


class TimeStampedModel(models.Model):
    created_at = models.DateTimeField("تاريخ الإنشاء", auto_now_add=True)
    updated_at = models.DateTimeField("آخر تحديث", auto_now=True)

    class Meta:
        abstract = True


class StoreSettings(TimeStampedModel):
    store_name = models.CharField("اسم المتجر", max_length=120, default="لُمعة")
    logo = models.ImageField("الشعار", upload_to="settings/", blank=True, validators=[validate_image_upload])
    favicon = models.ImageField("أيقونة الموقع", upload_to="settings/", blank=True, validators=[validate_image_upload])
    phone = models.CharField("رقم الهاتف", max_length=30, blank=True)
    whatsapp = models.CharField("واتساب", max_length=30, blank=True)
    email = models.EmailField("البريد الإلكتروني", blank=True)
    facebook = models.URLField("فيسبوك", blank=True)
    instagram = models.URLField("إنستجرام", blank=True)
    tiktok = models.URLField("تيك توك", blank=True)
    address = models.CharField("عنوان المتجر", max_length=255, blank=True)
    instapay_account_name = models.CharField("اسم حساب InstaPay", max_length=120, blank=True)
    instapay_address = models.CharField("رقم أو عنوان InstaPay", max_length=120, blank=True)
    currency = models.CharField("العملة", max_length=12, default="ج.م")
    free_shipping_threshold = models.DecimalField(
        "حد الشحن المجاني", max_digits=10, decimal_places=2, null=True, blank=True
    )
    header_announcement = models.CharField(
        "الإعلان العلوي", max_length=255, default="شحن مجاني للطلبات المختارة"
    )
    whatsapp_enabled = models.BooleanField("إظهار زر واتساب", default=True)
    whatsapp_message = models.CharField(
        "رسالة واتساب الافتراضية", max_length=255, default="مرحبًا، أريد الاستفسار عن منتجاتكم"
    )

    class Meta:
        verbose_name = "إعدادات المتجر"
        verbose_name_plural = "إعدادات المتجر"

    def save(self, *args, **kwargs):
        self.pk = 1
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        return None

    @classmethod
    def load(cls):
        instance, _ = cls.objects.get_or_create(pk=1)
        return instance

    def __str__(self):
        return self.store_name


class Banner(TimeStampedModel):
    class Position(models.TextChoices):
        HERO = "hero", "الرئيسي"
        PROMO = "promo", "ترويجي"

    position = models.CharField("الموضع", max_length=20, choices=Position.choices)
    title = models.CharField("العنوان", max_length=180)
    subtitle = models.CharField("النص", max_length=300, blank=True)
    button_text = models.CharField("نص الزر", max_length=60, blank=True)
    button_url = models.CharField("رابط الزر", max_length=255, default="/products/")
    image = models.ImageField("الصورة", upload_to="banners/", validators=[validate_image_upload])
    is_active = models.BooleanField("نشط", default=True)
    order = models.PositiveSmallIntegerField("الترتيب", default=0)

    class Meta:
        ordering = ["order", "-created_at"]
        verbose_name = "بانر"
        verbose_name_plural = "البانرات"
        indexes = [models.Index(fields=["position", "is_active", "order"])]

    def __str__(self):
        return self.title


class ContentPage(TimeStampedModel):
    slug = models.SlugField("الرابط", max_length=100, unique=True, allow_unicode=True)
    title = models.CharField("العنوان", max_length=180)
    content = models.TextField("المحتوى")
    meta_title = models.CharField("عنوان SEO", max_length=180, blank=True)
    meta_description = models.CharField("وصف SEO", max_length=300, blank=True)
    is_active = models.BooleanField("منشورة", default=True)

    class Meta:
        verbose_name = "صفحة محتوى"
        verbose_name_plural = "صفحات المحتوى"
        ordering = ["title"]

    def get_absolute_url(self):
        return reverse("core:page", kwargs={"slug": self.slug})

    def __str__(self):
        return self.title


class ContactMessage(TimeStampedModel):
    name = models.CharField("الاسم", max_length=120)
    phone = models.CharField("الهاتف", max_length=30)
    email = models.EmailField("البريد الإلكتروني", blank=True)
    subject = models.CharField("الموضوع", max_length=180)
    message = models.TextField("الرسالة")
    is_read = models.BooleanField("تمت القراءة", default=False)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "رسالة تواصل"
        verbose_name_plural = "رسائل التواصل"

    def __str__(self):
        return f"{self.name} - {self.subject}"


class SocialGalleryImage(TimeStampedModel):
    image = models.ImageField("الصورة", upload_to="gallery/", validators=[validate_image_upload])
    alt_text = models.CharField("النص البديل", max_length=180)
    link = models.URLField("الرابط", blank=True)
    is_active = models.BooleanField("نشطة", default=True)
    order = models.PositiveSmallIntegerField("الترتيب", default=0)

    class Meta:
        ordering = ["order", "-created_at"]
        verbose_name = "صورة اجتماعية"
        verbose_name_plural = "المعرض الاجتماعي"

    def __str__(self):
        return self.alt_text


class RoutineStep(TimeStampedModel):
    title = models.CharField("عنوان الخطوة", max_length=100)
    description = models.CharField("الوصف", max_length=180, blank=True)
    image = models.ImageField("الصورة", upload_to="routine/", blank=True, validators=[validate_image_upload])
    category = models.ForeignKey(
        "products.Category", verbose_name="التصنيف", on_delete=models.SET_NULL, null=True, blank=True
    )
    product = models.ForeignKey(
        "products.Product", verbose_name="المنتج", on_delete=models.SET_NULL, null=True, blank=True
    )
    order = models.PositiveSmallIntegerField("الترتيب", default=1)
    is_active = models.BooleanField("نشطة", default=True)

    class Meta:
        ordering = ["order"]
        verbose_name = "خطوة روتين"
        verbose_name_plural = "روتين العناية"

    def get_url(self):
        if self.product_id:
            return self.product.get_absolute_url()
        if self.category_id:
            return self.category.get_absolute_url()
        return reverse("products:list")

    def __str__(self):
        return self.title
