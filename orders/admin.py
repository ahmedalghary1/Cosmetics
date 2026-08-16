from django.contrib import admin

from .models import (
    Coupon, CouponRedemption, InventoryReservation, Order, OrderAuditLog,
    OrderItem, ReturnRequest, ReturnRequestItem, ShippingZone,
)


class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 0
    readonly_fields = ["product_name", "sku", "quantity", "unit_price", "total_price"]


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ["order_number", "full_name", "total", "payment_method", "payment_status", "status", "created_at"]
    list_filter = ["status", "payment_method", "payment_status"]
    search_fields = ["order_number", "full_name", "phone"]
    inlines = [OrderItemInline]
    exclude = ["payment_receipt"]
    readonly_fields = [
        field.name for field in Order._meta.fields
        if field.name not in {"id", "payment_receipt"}
    ]

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


admin.site.register([
    ShippingZone, Coupon, CouponRedemption, InventoryReservation,
    OrderAuditLog, ReturnRequest, ReturnRequestItem,
])
