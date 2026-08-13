from django.contrib import admin

from .models import Coupon, Order, OrderItem, ShippingZone


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


admin.site.register([ShippingZone, Coupon])
