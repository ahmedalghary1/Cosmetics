from decimal import Decimal

from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models
from django.db.models import F, Q
from django.urls import reverse
from django.utils import timezone
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
        now = timezone.now()
        return self.filter(is_active=True, category__is_active=True).filter(
            Q(source_bundle_offer__isnull=True)
            | Q(
                source_bundle_offer__sell_as_bundle=True,
                source_bundle_offer__is_active=True,
            )
        ).filter(
            Q(source_bundle_offer__isnull=True)
            | Q(source_bundle_offer__starts_at__isnull=True)
            | Q(source_bundle_offer__starts_at__lte=now)
        ).filter(
            Q(source_bundle_offer__isnull=True)
            | Q(source_bundle_offer__ends_at__isnull=True)
            | Q(source_bundle_offer__ends_at__gte=now)
        )


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
    price = models.DecimalField(
        "السعر", max_digits=10, decimal_places=2,
        validators=[MinValueValidator(Decimal("0.00"))],
    )
    old_price = models.DecimalField(
        "السعر القديم", max_digits=10, decimal_places=2, null=True, blank=True,
        validators=[MinValueValidator(Decimal("0.00"))],
    )
    stock_quantity = models.PositiveIntegerField("المخزون", default=0)
    reserved_quantity = models.PositiveIntegerField("الكمية المحجوزة", default=0, editable=False)
    is_bundle = models.BooleanField(
        "باقة / بوكس",
        default=False,
        help_text="الباقة تُباع كمنتج واحد ويُخصم مخزون مكوّناتها تلقائيًا.",
    )
    has_variants = models.BooleanField("له خيارات", default=False)
    brand = models.CharField("العلامة التجارية", max_length=120, blank=True)
    country_of_origin = models.CharField("بلد المنشأ", max_length=120, blank=True)
    key_ingredients = models.TextField("المكونات الفعالة", blank=True)
    benefits = models.TextField("الفوائد", blank=True)
    warnings = models.TextField("التحذيرات", blank=True)
    suitable_for = models.CharField("مناسب لـ", max_length=255, blank=True)
    skin_types = models.CharField("أنواع البشرة", max_length=255, blank=True)
    hair_types = models.CharField("أنواع الشعر", max_length=255, blank=True)
    size_label = models.CharField("الحجم", max_length=80, blank=True)
    pao_months = models.PositiveSmallIntegerField("الصلاحية بعد الفتح (شهر)", null=True, blank=True)
    cruelty_free = models.BooleanField("غير مجرب على الحيوانات", null=True, blank=True)
    vegan = models.BooleanField("نباتي", null=True, blank=True)
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
        constraints = [
            models.CheckConstraint(condition=Q(price__gte=0), name="product_price_nonnegative"),
            models.CheckConstraint(condition=Q(stock_quantity__gte=0), name="product_stock_nonnegative"),
            models.CheckConstraint(condition=Q(reserved_quantity__gte=0), name="product_reserved_nonnegative"),
            models.CheckConstraint(
                condition=Q(reserved_quantity__lte=F("stock_quantity")),
                name="product_reserved_lte_stock",
            ),
            models.CheckConstraint(
                condition=Q(old_price__isnull=True) | Q(old_price__gt=F("price")),
                name="product_old_price_gt_price",
            ),
        ]

    def clean(self):
        if self.old_price is not None and self.old_price <= self.price:
            raise ValidationError({"old_price": "يجب أن يكون السعر القديم أكبر من السعر الحالي."})
        if self.reserved_quantity > self.stock_quantity:
            raise ValidationError({"stock_quantity": "المخزون لا يمكن أن يقل عن الكمية المحجوزة."})
        if self.is_bundle and self.has_variants:
            raise ValidationError({"has_variants": "لا يمكن إضافة خيارات مباشرة للباقة؛ حددي خيارات مكوّناتها بدلًا من ذلك."})

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = unique_slug(Product, self.name, self.pk)
        super().save(*args, **kwargs)

    @property
    def in_stock(self):
        return self.available_stock > 0

    @property
    def available_stock(self):
        if self.is_bundle and self.pk:
            items = list(self.bundle_items.select_related("product", "product__category", "variant"))
            if not items:
                return 0
            if any(
                not item.product.is_active
                or not item.product.category.is_active
                or (item.variant_id and not item.variant.is_active)
                for item in items
            ):
                return 0
            return min(
                (item.variant.available_stock if item.variant_id else item.product.available_stock)
                // item.quantity
                for item in items
            )
        if self.has_variants and self.pk:
            return sum(variant.available_stock for variant in self.variants.filter(is_active=True))
        return max(self.stock_quantity - self.reserved_quantity, 0)

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


class VariantOption(TimeStampedModel):
    class Type(models.TextChoices):
        SIZE = "size", "الحجم"
        SCENT = "scent", "الرائحة"
        CONCENTRATION = "concentration", "التركيز"
        SPF = "spf", "درجة الحماية SPF"
        FORMULA = "formula", "التركيبة"

    option_type = models.CharField("نوع الخيار", max_length=24, choices=Type.choices)
    value = models.CharField("القيمة", max_length=100)
    order = models.PositiveSmallIntegerField("الترتيب", default=0)

    class Meta:
        ordering = ["option_type", "order", "value"]
        constraints = [
            models.UniqueConstraint(fields=["option_type", "value"], name="unique_variant_option_value"),
        ]
        verbose_name = "خيار منتج"
        verbose_name_plural = "خيارات المنتجات"

    def __str__(self):
        return f"{self.get_option_type_display()}: {self.value}"


class ProductVariant(TimeStampedModel):
    product = models.ForeignKey(Product, verbose_name="المنتج", related_name="variants", on_delete=models.CASCADE)
    sku = models.CharField("SKU", max_length=60, unique=True)
    options = models.ManyToManyField(VariantOption, verbose_name="الخيارات", related_name="variants", blank=True)
    option_summary = models.CharField("وصف الخيار", max_length=220)
    price = models.DecimalField(
        "سعر الخيار", max_digits=10, decimal_places=2, null=True, blank=True,
        validators=[MinValueValidator(Decimal("0.00"))],
        help_text="اتركه فارغًا لاستخدام سعر المنتج.",
    )
    old_price = models.DecimalField(
        "السعر القديم", max_digits=10, decimal_places=2, null=True, blank=True,
        validators=[MinValueValidator(Decimal("0.00"))],
    )
    stock_quantity = models.PositiveIntegerField("المخزون", default=0)
    reserved_quantity = models.PositiveIntegerField("الكمية المحجوزة", default=0, editable=False)
    barcode = models.CharField("الباركود", max_length=80, blank=True, db_index=True)
    weight_grams = models.PositiveIntegerField("الوزن (جرام)", null=True, blank=True)
    is_active = models.BooleanField("نشط", default=True)

    class Meta:
        ordering = ["product", "option_summary"]
        indexes = [models.Index(fields=["product", "is_active"])]
        constraints = [
            models.CheckConstraint(condition=Q(stock_quantity__gte=0), name="variant_stock_nonnegative"),
            models.CheckConstraint(condition=Q(reserved_quantity__gte=0), name="variant_reserved_nonnegative"),
            models.CheckConstraint(
                condition=Q(reserved_quantity__lte=F("stock_quantity")),
                name="variant_reserved_lte_stock",
            ),
            models.CheckConstraint(
                condition=Q(old_price__isnull=True) | Q(price__isnull=True) | Q(old_price__gt=F("price")),
                name="variant_old_price_gt_price",
            ),
        ]
        verbose_name = "خيار منتج"
        verbose_name_plural = "خيارات المنتجات"

    @property
    def effective_price(self):
        return self.price if self.price is not None else self.product.price

    @property
    def available_stock(self):
        return max(self.stock_quantity - self.reserved_quantity, 0)

    def clean(self):
        if self.old_price is not None:
            current = self.effective_price
            if self.old_price <= current:
                raise ValidationError({"old_price": "يجب أن يكون السعر القديم أكبر من السعر الحالي."})
        if self.reserved_quantity > self.stock_quantity:
            raise ValidationError({"stock_quantity": "المخزون لا يمكن أن يقل عن الكمية المحجوزة."})

    def __str__(self):
        return f"{self.product.name} - {self.option_summary}"


class BundleItem(models.Model):
    bundle = models.ForeignKey(
        Product, verbose_name="الباقة", related_name="bundle_items", on_delete=models.CASCADE,
    )
    product = models.ForeignKey(
        Product, verbose_name="المنتج داخل الباقة", related_name="included_in_bundles", on_delete=models.PROTECT,
    )
    variant = models.ForeignKey(
        ProductVariant, verbose_name="الخيار", related_name="included_in_bundles",
        on_delete=models.PROTECT, null=True, blank=True,
    )
    quantity = models.PositiveSmallIntegerField("الكمية داخل الباقة", default=1)

    class Meta:
        ordering = ["id"]
        verbose_name = "مكوّن باقة"
        verbose_name_plural = "مكوّنات الباقات"
        constraints = [
            models.CheckConstraint(condition=Q(quantity__gt=0), name="bundle_item_quantity_positive"),
            models.UniqueConstraint(
                fields=["bundle", "product", "variant"],
                condition=Q(variant__isnull=False),
                name="unique_bundle_variant_item",
            ),
            models.UniqueConstraint(
                fields=["bundle", "product"],
                condition=Q(variant__isnull=True),
                name="unique_bundle_product_item",
            ),
        ]

    def clean(self):
        errors = {}
        if self.bundle_id and not self.bundle.is_bundle:
            errors["bundle"] = "يجب تفعيل خيار «باقة / بوكس» للمنتج الرئيسي."
        if self.bundle_id and self.product_id == self.bundle_id:
            errors["product"] = "لا يمكن أن تحتوي الباقة على نفسها."
        if self.product_id and self.product.is_bundle:
            errors["product"] = "لا يمكن وضع باقة داخل باقة أخرى."
        if self.variant_id and self.variant.product_id != self.product_id:
            errors["variant"] = "الخيار لا يتبع المنتج المحدد."
        if self.product_id and self.product.has_variants and not self.variant_id:
            errors["variant"] = "اختيار النوع مطلوب لهذا المنتج."
        if self.product_id and not self.product.has_variants and self.variant_id:
            errors["variant"] = "هذا المنتج لا يحتوي على خيارات."
        if errors:
            raise ValidationError(errors)

    def __str__(self):
        variant = f" — {self.variant.option_summary}" if self.variant_id else ""
        return f"{self.product.name}{variant} × {self.quantity}"


class InventoryBatch(TimeStampedModel):
    product = models.ForeignKey(Product, verbose_name="المنتج", related_name="batches", on_delete=models.PROTECT)
    variant = models.ForeignKey(
        ProductVariant, verbose_name="الخيار", related_name="batches",
        on_delete=models.PROTECT, null=True, blank=True,
    )
    batch_number = models.CharField("رقم التشغيلة", max_length=80)
    quantity = models.PositiveIntegerField("الكمية", default=0)
    reserved_quantity = models.PositiveIntegerField("الكمية المحجوزة", default=0, editable=False)
    manufacturing_date = models.DateField("تاريخ الإنتاج", null=True, blank=True)
    expiry_date = models.DateField("تاريخ الانتهاء", null=True, blank=True, db_index=True)
    received_date = models.DateField("تاريخ الاستلام", null=True, blank=True)
    purchase_cost = models.DecimalField(
        "تكلفة الوحدة", max_digits=10, decimal_places=2, default=0,
        validators=[MinValueValidator(Decimal("0.00"))],
    )
    is_active = models.BooleanField("نشطة", default=True)

    class Meta:
        ordering = [F("expiry_date").asc(nulls_last=True), "received_date", "id"]
        indexes = [models.Index(fields=["product", "variant", "is_active", "expiry_date"])]
        constraints = [
            models.UniqueConstraint(
                fields=["product", "variant", "batch_number"],
                condition=Q(variant__isnull=False),
                name="unique_variant_inventory_batch",
            ),
            models.UniqueConstraint(
                fields=["product", "batch_number"],
                condition=Q(variant__isnull=True),
                name="unique_product_inventory_batch",
            ),
            models.CheckConstraint(condition=Q(quantity__gte=0), name="batch_quantity_nonnegative"),
            models.CheckConstraint(condition=Q(reserved_quantity__gte=0), name="batch_reserved_nonnegative"),
            models.CheckConstraint(condition=Q(reserved_quantity__lte=F("quantity")), name="batch_reserved_lte_quantity"),
            models.CheckConstraint(condition=Q(purchase_cost__gte=0), name="batch_cost_nonnegative"),
        ]
        verbose_name = "تشغيلة مخزون"
        verbose_name_plural = "تشغيلات المخزون"

    @property
    def available_quantity(self):
        return max(self.quantity - self.reserved_quantity, 0)

    def clean(self):
        if self.variant_id and self.variant.product_id != self.product_id:
            raise ValidationError({"variant": "الخيار لا يتبع هذا المنتج."})
        if self.manufacturing_date and self.expiry_date and self.expiry_date <= self.manufacturing_date:
            raise ValidationError({"expiry_date": "تاريخ الانتهاء يجب أن يكون بعد تاريخ الإنتاج."})
        if self.reserved_quantity > self.quantity:
            raise ValidationError({"quantity": "الكمية لا يمكن أن تقل عن المحجوز."})

    def __str__(self):
        return f"{self.product.name} / {self.batch_number}"


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
