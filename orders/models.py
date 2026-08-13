from decimal import Decimal, ROUND_HALF_UP
import uuid

from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models
from django.urls import reverse
from django.utils import timezone

from core.models import TimeStampedModel
from core.validators import validate_image_upload


class ShippingZone(TimeStampedModel):
    name = models.CharField("المحافظة", max_length=100, unique=True)
    shipping_cost = models.DecimalField(
        "تكلفة الشحن", max_digits=9, decimal_places=2,
        validators=[MinValueValidator(Decimal("0"))],
    )
    is_active = models.BooleanField("نشطة", default=True)
    order = models.PositiveSmallIntegerField("الترتيب", default=0)

    class Meta:
        ordering = ["order", "name"]
        verbose_name = "منطقة شحن"
        verbose_name_plural = "مناطق الشحن"

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
    minimum_order = models.DecimalField("الحد الأدنى للطلب", max_digits=10, decimal_places=2, default=0)
    start_date = models.DateTimeField("تاريخ البداية")
    end_date = models.DateTimeField("تاريخ النهاية")
    usage_limit = models.PositiveIntegerField("حد الاستخدام", null=True, blank=True)
    used_count = models.PositiveIntegerField("مرات الاستخدام", default=0, editable=False)
    is_active = models.BooleanField("نشط", default=True)

    class Meta:
        verbose_name = "كوبون خصم"
        verbose_name_plural = "كوبونات الخصم"
        indexes = [models.Index(fields=["code", "is_active"])]

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

    class Status(models.TextChoices):
        NEW = "new", "طلب جديد"
        CONFIRMED = "confirmed", "تم التأكيد"
        PREPARING = "preparing", "جاري التجهيز"
        SHIPPED = "shipped", "تم الشحن"
        DELIVERED = "delivered", "تم التسليم"
        CANCELLED = "cancelled", "ملغي"

    order_number = models.CharField("رقم الطلب", max_length=30, unique=True, db_index=True)
    access_token = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, verbose_name="المستخدم", related_name="orders",
        on_delete=models.SET_NULL, null=True, blank=True,
    )
    full_name = models.CharField("الاسم بالكامل", max_length=150)
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
        validators=[validate_image_upload],
    )
    payment_note = models.TextField("ملاحظة مراجعة الدفع", blank=True)
    status = models.CharField(
        "حالة الطلب", max_length=20, choices=Status.choices,
        default=Status.NEW, db_index=True,
    )
    stock_released = models.BooleanField(default=False, editable=False)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "طلب"
        verbose_name_plural = "الطلبات"
        indexes = [
            models.Index(fields=["-created_at", "status"]),
            models.Index(fields=["payment_status", "-created_at"]),
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
    product_name = models.CharField("اسم المنتج", max_length=180)
    sku = models.CharField("SKU", max_length=60)
    quantity = models.PositiveIntegerField("الكمية")
    unit_price = models.DecimalField("سعر الوحدة", max_digits=10, decimal_places=2)
    total_price = models.DecimalField("الإجمالي", max_digits=11, decimal_places=2)

    class Meta:
        verbose_name = "عنصر طلب"
        verbose_name_plural = "عناصر الطلب"

    def __str__(self):
        return f"{self.product_name} × {self.quantity}"
