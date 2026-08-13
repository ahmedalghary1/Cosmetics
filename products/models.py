from decimal import Decimal

from django.db import models
from django.urls import reverse
from django.utils.text import slugify

from core.models import TimeStampedModel
from core.validators import validate_image_upload


class Category(TimeStampedModel):
    name = models.CharField("الاسم", max_length=120, unique=True)
    slug = models.SlugField("الرابط", max_length=140, unique=True, allow_unicode=True, blank=True)
    image = models.ImageField("الصورة", upload_to="categories/", blank=True, validators=[validate_image_upload])
    description = models.TextField("الوصف", blank=True)
    is_active = models.BooleanField("نشط", default=True)
    order = models.PositiveSmallIntegerField("الترتيب", default=0)

    class Meta:
        ordering = ["order", "name"]
        verbose_name = "تصنيف"
        verbose_name_plural = "التصنيفات"
        indexes = [models.Index(fields=["is_active", "order"])]

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = unique_slug(Category, self.name, self.pk)
        super().save(*args, **kwargs)

    def get_absolute_url(self):
        return reverse("product_categories:detail", kwargs={"category_slug": self.slug})

    def __str__(self):
        return self.name


class ProductQuerySet(models.QuerySet):
    def active(self):
        return self.filter(is_active=True, category__is_active=True)


class Product(TimeStampedModel):
    name = models.CharField("اسم المنتج", max_length=180)
    slug = models.SlugField("الرابط", max_length=210, unique=True, allow_unicode=True, blank=True)
    sku = models.CharField("SKU", max_length=60, unique=True)
    category = models.ForeignKey(
        Category, verbose_name="التصنيف", related_name="products", on_delete=models.PROTECT
    )
    short_description = models.CharField("وصف مختصر", max_length=300, blank=True)
    description = models.TextField("الوصف")
    ingredients = models.TextField("المكونات", blank=True)
    usage = models.TextField("طريقة الاستخدام", blank=True)
    price = models.DecimalField("السعر", max_digits=10, decimal_places=2)
    old_price = models.DecimalField("السعر القديم", max_digits=10, decimal_places=2, null=True, blank=True)
    stock_quantity = models.PositiveIntegerField("المخزون", default=0)
    main_image = models.ImageField("الصورة الرئيسية", upload_to="products/", blank=True, validators=[validate_image_upload])
    is_active = models.BooleanField("نشط", default=True)
    is_featured = models.BooleanField("مميز", default=False)
    is_best_seller = models.BooleanField("الأكثر مبيعًا", default=False)
    is_new = models.BooleanField("جديد", default=False)
    sales_count = models.PositiveIntegerField("عدد المبيعات", default=0, editable=False)
    meta_title = models.CharField("عنوان SEO", max_length=180, blank=True)
    meta_description = models.CharField("وصف SEO", max_length=300, blank=True)

    objects = ProductQuerySet.as_manager()

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "منتج"
        verbose_name_plural = "المنتجات"
        indexes = [
            models.Index(fields=["is_active", "-created_at"]),
            models.Index(fields=["is_best_seller", "-sales_count"]),
            models.Index(fields=["category", "is_active"]),
        ]

    def clean(self):
        from django.core.exceptions import ValidationError

        if self.old_price is not None and self.old_price <= self.price:
            raise ValidationError({"old_price": "يجب أن يكون السعر القديم أكبر من السعر الحالي."})

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = unique_slug(Product, self.name, self.pk)
        super().save(*args, **kwargs)

    @property
    def in_stock(self):
        return self.stock_quantity > 0

    @property
    def discount_percentage(self):
        if not self.old_price or self.old_price <= self.price:
            return 0
        return int(((self.old_price - self.price) / self.old_price) * Decimal("100"))

    def get_absolute_url(self):
        return reverse("products:detail", kwargs={"slug": self.slug})

    def __str__(self):
        return self.name


class ProductImage(TimeStampedModel):
    product = models.ForeignKey(Product, related_name="images", on_delete=models.CASCADE)
    image = models.ImageField("الصورة", upload_to="products/gallery/", validators=[validate_image_upload])
    alt_text = models.CharField("النص البديل", max_length=180, blank=True)
    order = models.PositiveSmallIntegerField("الترتيب", default=0)

    class Meta:
        ordering = ["order", "id"]
        verbose_name = "صورة منتج"
        verbose_name_plural = "صور المنتجات"

    def __str__(self):
        return self.alt_text or self.product.name


def unique_slug(model, value, instance_pk=None):
    base = slugify(value, allow_unicode=True)[:180] or "item"
    slug = base
    counter = 2
    queryset = model.objects.all()
    if instance_pk:
        queryset = queryset.exclude(pk=instance_pk)
    while queryset.filter(slug=slug).exists():
        suffix = f"-{counter}"
        slug = f"{base[: 200 - len(suffix)]}{suffix}"
        counter += 1
    return slug
