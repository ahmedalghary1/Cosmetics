from django.contrib import admin

from .models import Category, Product, ProductImage


class ProductImageInline(admin.TabularInline):
    model = ProductImage
    extra = 0


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ["name", "category", "price", "stock_quantity", "is_active"]
    list_filter = ["category", "is_active", "is_best_seller", "is_new"]
    search_fields = ["name", "sku"]
    inlines = [ProductImageInline]


admin.site.register(Category)
