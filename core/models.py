from django.db import models
from django.db.models import Q
from django.urls import reverse
from django.utils import timezone

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
    instapay_enabled = models.BooleanField("تفعيل الدفع عبر InstaPay", default=True)
    currency = models.CharField("العملة", max_length=12, default="ج.م")
    free_shipping_threshold = models.DecimalField(
        "حد الشحن المجاني", max_digits=10, decimal_places=2, null=True, blank=True
    )
    inventory_reservation_minutes = models.PositiveSmallIntegerField("مدة حجز المخزون (دقيقة)", default=30)
    return_window_days = models.PositiveSmallIntegerField("مدة طلب الإرجاع (يوم)", default=14)
    terms_version = models.CharField("نسخة الشروط", max_length=30, default="1.0")
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
    image = models.ImageField("الصورة (شاشات كبيرة)", upload_to="banners/", validators=[validate_image_upload])
    image_tablet = models.ImageField("صورة التابلت", upload_to="banners/", blank=True, null=True, validators=[validate_image_upload])
    image_mobile = models.ImageField("صورة الموبايل", upload_to="banners/", blank=True, null=True, validators=[validate_image_upload])
    is_active = models.BooleanField("نشط", default=True)
    order = models.PositiveSmallIntegerField("الترتيب", default=0)

    class Meta:
        ordering = ["order", "-created_at"]
        verbose_name = "بانر"
        verbose_name_plural = "البانرات"
        indexes = [models.Index(fields=["position", "is_active", "order"])]

    def __str__(self):
        return self.title


class OfferQuerySet(models.QuerySet):
    def current(self, at=None):
        at = at or timezone.now()
        return self.filter(is_active=True).filter(
            Q(starts_at__isnull=True) | Q(starts_at__lte=at),
            Q(ends_at__isnull=True) | Q(ends_at__gte=at),
        )


class Offer(TimeStampedModel):
    eyebrow = models.CharField("النص الصغير", max_length=80, default="وقت التدليل")
    title = models.CharField("عنوان العرض", max_length=180)
    subtitle = models.CharField("وصف العرض", max_length=300, blank=True)
    sell_as_bundle = models.BooleanField(
        "بيع العرض كباقة واحدة",
        default=False,
        help_text="يفتح العرض كمنتج واحد ويُضاف إلى السلة بضغطة واحدة.",
    )
    image = models.ImageField(
        "صورة العرض", upload_to="offers/", blank=True, validators=[validate_image_upload],
    )
    bundle_price = models.DecimalField(
        "سعر العرض كاملًا", max_digits=10, decimal_places=2, null=True, blank=True,
    )
    bundle_old_price = models.DecimalField(
        "السعر قبل العرض", max_digits=10, decimal_places=2, null=True, blank=True,
        help_text="اختياري؛ عند تركه فارغًا يُستخدم مجموع أسعار المنتجات.",
    )
    products = models.ManyToManyField(
        "products.Product", verbose_name="المنتجات", related_name="offer_campaigns"
    )
    bundle_product = models.OneToOneField(
        "products.Product", related_name="source_bundle_offer", on_delete=models.SET_NULL,
        null=True, blank=True, editable=False,
    )
    button_text = models.CharField("نص زر كل العروض", max_length=60, default="كل العروض")
    button_url = models.CharField(
        "رابط مخصص للزر", max_length=255, blank=True,
        help_text="يُترك فارغًا لعرض منتجات هذا العرض تلقائيًا.",
    )
    starts_at = models.DateTimeField("بداية العرض", null=True, blank=True)
    ends_at = models.DateTimeField("نهاية العرض", null=True, blank=True)
    is_active = models.BooleanField("نشط", default=True)
    order = models.PositiveSmallIntegerField("الترتيب", default=0)

    objects = OfferQuerySet.as_manager()

    class Meta:
        ordering = ["order", "-created_at"]
        verbose_name = "عرض"
        verbose_name_plural = "العروض"
        indexes = [models.Index(fields=["is_active", "order", "starts_at", "ends_at"])]

    def clean(self):
        from django.core.exceptions import ValidationError

        if self.starts_at and self.ends_at and self.ends_at <= self.starts_at:
            raise ValidationError({"ends_at": "يجب أن تكون نهاية العرض بعد بدايته."})

    def get_url(self):
        if self.sell_as_bundle and self.bundle_product_id:
            return self.bundle_product.get_absolute_url()
        if self.button_url:
            return self.button_url
        return f"{reverse('products:list')}?offer={self.pk}"

    def sync_bundle_product(self):
        from decimal import Decimal

        from products.models import BundleItem, Product

        if not self.pk:
            return None
        if not self.sell_as_bundle:
            if self.bundle_product_id:
                Product.objects.filter(pk=self.bundle_product_id).update(is_active=False)
            return None

        components = list(self.products.select_related("category").prefetch_related("categories"))
        if not components:
            return None
        old_price = self.bundle_old_price or sum(
            (product.price for product in components), Decimal("0.00")
        )
        defaults = {
            "name": self.title,
            "category": None,
            "short_description": self.subtitle,
            "description": self.subtitle or self.title,
            "price": self.bundle_price,
            "old_price": old_price,
            "stock_quantity": 0,
            "is_bundle": True,
            "has_variants": False,
            "main_image": self.image,
            "is_active": self.is_active,
            "is_featured": True,
        }
        if self.bundle_product_id:
            bundle = self.bundle_product
            for field, value in defaults.items():
                setattr(bundle, field, value)
            bundle.save()
        else:
            bundle = Product.objects.create(sku=f"OFFER-{self.pk}", **defaults)
            Offer.objects.filter(pk=self.pk).update(bundle_product=bundle)
            self.bundle_product = bundle
        bundle.categories.clear()
        BundleItem.objects.filter(bundle=bundle).delete()
        BundleItem.objects.bulk_create([
            BundleItem(bundle=bundle, product=product, quantity=1)
            for product in components
        ])
        return bundle

    def delete(self, *args, **kwargs):
        bundle_product_id = self.bundle_product_id
        result = super().delete(*args, **kwargs)
        if bundle_product_id:
            from products.models import Product

            Product.objects.filter(pk=bundle_product_id).update(is_active=False)
        return result

    @property
    def display_status(self):
        if not self.is_active:
            return "متوقف"
        now = timezone.now()
        if self.starts_at and self.starts_at > now:
            return "مجدول"
        if self.ends_at and self.ends_at < now:
            return "منتهي"
        return "ظاهر الآن"

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
        if self.slug == "من-نحن":
            return reverse("core:about")
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
