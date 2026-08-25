from decimal import Decimal, ROUND_HALF_UP
import uuid

from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models
from django.db.models import F, Q
from django.urls import reverse
from django.utils import timezone

from core.models import TimeStampedModel
from core.storage import private_media_storage
from core.validators import validate_image_upload


class ShippingZone(TimeStampedModel):
    name = models.CharField("المحافظة", max_length=100, unique=True)
    shipping_cost = models.DecimalField(
        "تكلفة الشحن", max_digits=9, decimal_places=2,
        validators=[MinValueValidator(Decimal("0"))],
    )
    is_active = models.BooleanField("نشطة", default=True)
    order = models.PositiveSmallIntegerField("الترتيب", default=0)
    estimated_delivery_min_days = models.PositiveSmallIntegerField("أقل مدة للتوصيل", default=2)
    estimated_delivery_max_days = models.PositiveSmallIntegerField("أقصى مدة للتوصيل", default=5)

    class Meta:
        ordering = ["order", "name"]
        verbose_name = "منطقة شحن"
        verbose_name_plural = "مناطق الشحن"
        constraints = [
            models.CheckConstraint(condition=Q(shipping_cost__gte=0), name="shipping_cost_nonnegative"),
            models.CheckConstraint(
                condition=Q(estimated_delivery_max_days__gte=F("estimated_delivery_min_days")),
                name="shipping_delivery_days_ordered",
            ),
        ]

    def __str__(self):
        return self.name


class Coupon(TimeStampedModel):
    class DiscountType(models.TextChoices):
        PERCENTAGE = "percentage", "نسبة مئوية"
        FIXED = "fixed", "قيمة ثابتة"

    code = models.CharField("الكود", max_length=40, unique=True)
    discount_type = models.CharField("نوع الخصم", max_length=20, choices=DiscountType.choices)
    value = models.DecimalField(
        "قيمة الخصم", max_digits=9, decimal_places=2,
        validators=[MinValueValidator(Decimal("0.01"))],
    )
    minimum_order = models.DecimalField(
        "الحد الأدنى للطلب", max_digits=10, decimal_places=2, default=0,
        validators=[MinValueValidator(Decimal("0.00"))],
    )
    start_date = models.DateTimeField("تاريخ البداية")
    end_date = models.DateTimeField("تاريخ النهاية")
    usage_limit = models.PositiveIntegerField("حد الاستخدام", null=True, blank=True)
    max_uses_per_customer = models.PositiveIntegerField("حد الاستخدام لكل عميل", null=True, blank=True)
    used_count = models.PositiveIntegerField("مرات الاستخدام", default=0, editable=False)
    products = models.ManyToManyField(
        "products.Product", verbose_name="منتجات محددة", related_name="coupons", blank=True,
    )
    categories = models.ManyToManyField(
        "products.Category", verbose_name="تصنيفات محددة", related_name="coupons", blank=True,
    )
    is_active = models.BooleanField("نشط", default=True)

    class Meta:
        verbose_name = "كوبون خصم"
        verbose_name_plural = "كوبونات الخصم"
        indexes = [models.Index(fields=["code", "is_active"])]
        constraints = [
            models.CheckConstraint(condition=Q(value__gt=0), name="coupon_value_positive"),
            models.CheckConstraint(condition=Q(minimum_order__gte=0), name="coupon_minimum_nonnegative"),
            models.CheckConstraint(condition=Q(end_date__gt=F("start_date")), name="coupon_dates_ordered"),
            models.CheckConstraint(
                condition=~Q(discount_type="percentage") | Q(value__lte=100),
                name="coupon_percentage_lte_100",
            ),
        ]

    def clean(self):
        from django.core.exceptions import ValidationError

        if self.start_date and self.end_date and self.end_date <= self.start_date:
            raise ValidationError({"end_date": "يجب أن يكون تاريخ النهاية بعد تاريخ البداية."})
        if self.discount_type == self.DiscountType.PERCENTAGE and self.value > 100:
            raise ValidationError({"value": "نسبة الخصم لا يمكن أن تتجاوز 100%."})

    def is_valid_for(self, subtotal):
        now = timezone.now()
        within_limit = self.usage_limit is None or self.used_count < self.usage_limit
        return (
            self.is_active
            and self.start_date <= now <= self.end_date
            and within_limit
            and subtotal >= self.minimum_order
        )

    def calculate_discount(self, subtotal):
        if not self.is_valid_for(subtotal):
            return Decimal("0.00")
        if self.discount_type == self.DiscountType.PERCENTAGE:
            discount = subtotal * (self.value / Decimal("100"))
        else:
            discount = self.value
        return min(discount, subtotal).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

    def save(self, *args, **kwargs):
        self.code = self.code.strip().upper()
        super().save(*args, **kwargs)

    def __str__(self):
        return self.code


class Order(TimeStampedModel):
    class PaymentMethod(models.TextChoices):
        CASH = "cash_on_delivery", "الدفع عند الاستلام"
        INSTAPAY = "instapay", "تحويل InstaPay"

    class PaymentStatus(models.TextChoices):
        UNPAID = "unpaid", "الدفع عند الاستلام"
        PENDING = "pending_verification", "في انتظار مراجعة التحويل"
        VERIFIED = "verified", "تم تأكيد الدفع"
        REJECTED = "rejected", "تم رفض إثبات الدفع"
        REFUNDED = "refunded", "تم رد المبلغ"

    class Status(models.TextChoices):
        NEW = "new", "طلب جديد"
        AWAITING_PAYMENT = "awaiting_payment", "في انتظار الدفع"
        CONFIRMED = "confirmed", "تم التأكيد"
        PREPARING = "preparing", "جاري التجهيز"
        SHIPPED = "shipped", "تم الشحن"
        DELIVERED = "delivered", "تم التسليم"
        CANCELLED = "cancelled", "ملغي"
        PAYMENT_FAILED = "payment_failed", "فشل الدفع"
        REFUNDED = "refunded", "مسترد"

    order_number = models.CharField("رقم الطلب", max_length=30, unique=True, db_index=True)
    idempotency_key = models.UUIDField("مفتاح عدم التكرار", default=uuid.uuid4, unique=True, editable=False)
    access_token = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, verbose_name="المستخدم", related_name="orders",
        on_delete=models.SET_NULL, null=True, blank=True,
    )
    full_name = models.CharField("الاسم بالكامل", max_length=150)
    email = models.EmailField("البريد الإلكتروني", blank=True)
    phone = models.CharField("رقم الهاتف", max_length=30, db_index=True)
    alternative_phone = models.CharField("رقم إضافي", max_length=30, blank=True)
    governorate = models.ForeignKey(
        ShippingZone, verbose_name="المحافظة", related_name="orders", on_delete=models.PROTECT,
    )
    city = models.CharField("المدينة / المنطقة", max_length=120)
    address = models.CharField("العنوان بالتفصيل", max_length=300)
    landmark = models.CharField("علامة مميزة", max_length=180, blank=True)
    notes = models.TextField("ملاحظات الطلب", blank=True)
    subtotal = models.DecimalField("المجموع الفرعي", max_digits=11, decimal_places=2)
    discount = models.DecimalField("الخصم", max_digits=11, decimal_places=2, default=0)
    shipping_cost = models.DecimalField("الشحن", max_digits=9, decimal_places=2)
    total = models.DecimalField("الإجمالي", max_digits=11, decimal_places=2)
    coupon = models.ForeignKey(Coupon, verbose_name="الكوبون", on_delete=models.SET_NULL, null=True, blank=True)
    payment_method = models.CharField("طريقة الدفع", max_length=30, choices=PaymentMethod.choices)
    payment_status = models.CharField("حالة الدفع", max_length=30, choices=PaymentStatus.choices)
    payment_receipt = models.ImageField(
        "إثبات التحويل", upload_to="payment_receipts/%Y/%m/", blank=True,
        validators=[validate_image_upload], storage=private_media_storage,
    )
    payment_note = models.TextField("ملاحظة مراجعة الدفع", blank=True)
    status = models.CharField(
        "حالة الطلب", max_length=20, choices=Status.choices,
        default=Status.NEW, db_index=True,
    )
    stock_released = models.BooleanField(default=False, editable=False)
    reservation_expires_at = models.DateTimeField("انتهاء حجز المخزون", null=True, blank=True, db_index=True)
    terms_version = models.CharField("نسخة الشروط", max_length=30, blank=True)
    terms_accepted_at = models.DateTimeField("وقت الموافقة على الشروط", null=True, blank=True)
    confirmed_at = models.DateTimeField("وقت التأكيد", null=True, blank=True)
    shipped_at = models.DateTimeField("وقت الشحن", null=True, blank=True)
    delivered_at = models.DateTimeField("وقت التسليم", null=True, blank=True)
    cancelled_at = models.DateTimeField("وقت الإلغاء/الفشل", null=True, blank=True)
    sales_counted = models.BooleanField(default=False, editable=False)
    coupon_consumed = models.BooleanField(default=False, editable=False)
    refunded_amount = models.DecimalField("المبلغ المسترد", max_digits=11, decimal_places=2, default=0)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "طلب"
        verbose_name_plural = "الطلبات"
        indexes = [
            models.Index(fields=["-created_at", "status"]),
            models.Index(fields=["payment_status", "-created_at"]),
        ]
        constraints = [
            models.CheckConstraint(condition=Q(subtotal__gte=0), name="order_subtotal_nonnegative"),
            models.CheckConstraint(condition=Q(discount__gte=0), name="order_discount_nonnegative"),
            models.CheckConstraint(condition=Q(shipping_cost__gte=0), name="order_shipping_nonnegative"),
            models.CheckConstraint(condition=Q(total__gte=0), name="order_total_nonnegative"),
            models.CheckConstraint(condition=Q(discount__lte=F("subtotal")), name="order_discount_lte_subtotal"),
            models.CheckConstraint(condition=Q(refunded_amount__gte=0), name="order_refund_nonnegative"),
            models.CheckConstraint(condition=Q(refunded_amount__lte=F("total")), name="order_refund_lte_total"),
        ]
        permissions = [
            ("transition_order", "Can transition order status"),
            ("verify_payment", "Can verify order payment"),
            ("view_payment_receipt", "Can view private payment receipt"),
            ("view_financial_reports", "Can view financial reports"),
        ]

    def get_success_url(self):
        return reverse("orders:success", kwargs={"order_number": self.order_number})

    def __str__(self):
        return self.order_number


class OrderItem(models.Model):
    order = models.ForeignKey(Order, verbose_name="الطلب", related_name="items", on_delete=models.CASCADE)
    product = models.ForeignKey(
        "products.Product", verbose_name="المنتج", related_name="order_items",
        on_delete=models.SET_NULL, null=True,
    )
    variant = models.ForeignKey(
        "products.ProductVariant", verbose_name="الخيار", related_name="order_items",
        on_delete=models.SET_NULL, null=True, blank=True,
    )
    product_name = models.CharField("اسم المنتج", max_length=180)
    variant_name = models.CharField("وصف الخيار", max_length=220, blank=True)
    sku = models.CharField("SKU", max_length=60)
    quantity = models.PositiveIntegerField("الكمية")
    unit_price = models.DecimalField("سعر الوحدة", max_digits=10, decimal_places=2)
    total_price = models.DecimalField("الإجمالي", max_digits=11, decimal_places=2)
    unit_cost = models.DecimalField("تكلفة الوحدة", max_digits=10, decimal_places=2, default=0)
    total_cost = models.DecimalField("إجمالي التكلفة", max_digits=11, decimal_places=2, default=0)

    class Meta:
        verbose_name = "عنصر طلب"
        verbose_name_plural = "عناصر الطلب"
        constraints = [
            models.CheckConstraint(condition=Q(quantity__gt=0), name="order_item_quantity_positive"),
            models.CheckConstraint(condition=Q(unit_price__gte=0), name="order_item_price_nonnegative"),
            models.CheckConstraint(condition=Q(total_price__gte=0), name="order_item_total_nonnegative"),
            models.CheckConstraint(condition=Q(unit_cost__gte=0), name="order_item_cost_nonnegative"),
            models.CheckConstraint(condition=Q(total_cost__gte=0), name="order_item_total_cost_nonnegative"),
        ]

    def __str__(self):
        return f"{self.product_name} × {self.quantity}"


class OrderItemBundleComponent(models.Model):
    order_item = models.ForeignKey(
        OrderItem, related_name="bundle_components", on_delete=models.CASCADE,
    )
    product = models.ForeignKey(
        "products.Product", related_name="order_bundle_component_snapshots",
        on_delete=models.SET_NULL, null=True,
    )
    variant = models.ForeignKey(
        "products.ProductVariant", related_name="order_bundle_component_snapshots",
        on_delete=models.SET_NULL, null=True, blank=True,
    )
    product_name = models.CharField("اسم مكوّن الباقة", max_length=180)
    variant_name = models.CharField("وصف الخيار", max_length=220, blank=True)
    sku = models.CharField("SKU", max_length=60)
    quantity_per_bundle = models.PositiveSmallIntegerField("الكمية في الباقة")

    class Meta:
        verbose_name = "مكوّن باقة في الطلب"
        verbose_name_plural = "مكوّنات الباقات في الطلب"
        constraints = [
            models.CheckConstraint(
                condition=Q(quantity_per_bundle__gt=0),
                name="order_bundle_component_quantity_positive",
            ),
        ]

    def __str__(self):
        return f"{self.product_name} × {self.quantity_per_bundle}"


class InventoryReservation(TimeStampedModel):
    class Status(models.TextChoices):
        ACTIVE = "active", "نشط"
        CONSUMED = "consumed", "تم الخصم"
        RELEASED = "released", "تم التحرير"
        EXPIRED = "expired", "منتهي"

    order = models.ForeignKey(Order, verbose_name="الطلب", related_name="reservations", on_delete=models.CASCADE)
    product = models.ForeignKey(
        "products.Product", verbose_name="المنتج", related_name="reservations", on_delete=models.PROTECT,
    )
    variant = models.ForeignKey(
        "products.ProductVariant", verbose_name="الخيار", related_name="reservations",
        on_delete=models.PROTECT, null=True, blank=True,
    )
    quantity = models.PositiveIntegerField("الكمية")
    reserved_until = models.DateTimeField("محجوز حتى", db_index=True)
    status = models.CharField("الحالة", max_length=16, choices=Status.choices, default=Status.ACTIVE, db_index=True)

    class Meta:
        constraints = [
            models.CheckConstraint(condition=Q(quantity__gt=0), name="reservation_quantity_positive"),
            models.UniqueConstraint(
                fields=["order", "product", "variant"],
                condition=Q(variant__isnull=False),
                name="unique_order_variant_reservation",
            ),
            models.UniqueConstraint(
                fields=["order", "product"],
                condition=Q(variant__isnull=True),
                name="unique_order_product_reservation",
            ),
        ]
        indexes = [models.Index(fields=["status", "reserved_until"])]
        verbose_name = "حجز مخزون"
        verbose_name_plural = "حجوزات المخزون"


class ReservationBatchAllocation(models.Model):
    reservation = models.ForeignKey(
        InventoryReservation, related_name="batch_allocations", on_delete=models.CASCADE,
    )
    batch = models.ForeignKey(
        "products.InventoryBatch", related_name="reservation_allocations", on_delete=models.PROTECT,
    )
    quantity = models.PositiveIntegerField("الكمية")

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["reservation", "batch"], name="unique_reservation_batch"),
            models.CheckConstraint(condition=Q(quantity__gt=0), name="allocation_quantity_positive"),
        ]


class CouponRedemption(TimeStampedModel):
    class Status(models.TextChoices):
        RESERVED = "reserved", "محجوز"
        CONSUMED = "consumed", "مستخدم"
        RELEASED = "released", "محرر"

    coupon = models.ForeignKey(Coupon, related_name="redemptions", on_delete=models.PROTECT)
    order = models.OneToOneField(Order, related_name="coupon_redemption", on_delete=models.CASCADE)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, related_name="coupon_redemptions",
        on_delete=models.SET_NULL, null=True, blank=True,
    )
    customer_key = models.CharField(max_length=160, db_index=True)
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.RESERVED, db_index=True)

    class Meta:
        indexes = [models.Index(fields=["coupon", "customer_key", "status"])]


class OrderAuditLog(models.Model):
    order = models.ForeignKey(Order, related_name="audit_logs", on_delete=models.CASCADE)
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL, related_name="order_audit_logs",
        on_delete=models.SET_NULL, null=True, blank=True,
    )
    action = models.CharField(max_length=80)
    old_values = models.JSONField(default=dict, blank=True)
    new_values = models.JSONField(default=dict, blank=True)
    note = models.TextField(blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-created_at"]


class ReturnRequest(TimeStampedModel):
    class Status(models.TextChoices):
        REQUESTED = "requested", "قيد المراجعة"
        APPROVED = "approved", "مقبول"
        REJECTED = "rejected", "مرفوض"
        RECEIVED = "received", "تم استلام المرتجع"
        REFUNDED = "refunded", "تم رد المبلغ"

    order = models.ForeignKey(
        Order, verbose_name="الطلب", related_name="return_requests", on_delete=models.PROTECT,
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, related_name="return_requests", on_delete=models.SET_NULL, null=True, blank=True,
    )
    reason = models.CharField("سبب الإرجاع", max_length=180)
    customer_note = models.TextField("تفاصيل العميل", blank=True)
    admin_note = models.TextField("ملاحظات الإدارة", blank=True)
    status = models.CharField(
        "الحالة", max_length=16, choices=Status.choices,
        default=Status.REQUESTED, db_index=True,
    )
    refund_amount = models.DecimalField("المبلغ المسترد", max_digits=11, decimal_places=2, default=0)

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.CheckConstraint(condition=Q(refund_amount__gte=0), name="return_refund_nonnegative"),
        ]


class ReturnRequestItem(models.Model):
    return_request = models.ForeignKey(ReturnRequest, related_name="items", on_delete=models.CASCADE)
    order_item = models.ForeignKey(OrderItem, related_name="return_items", on_delete=models.PROTECT)
    quantity = models.PositiveIntegerField("الكمية")
    restockable = models.BooleanField("صالح للإعادة إلى المخزون", default=False)
    restocked = models.BooleanField(default=False, editable=False)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["return_request", "order_item"], name="unique_return_order_item"),
            models.CheckConstraint(condition=Q(quantity__gt=0), name="return_item_quantity_positive"),
        ]
