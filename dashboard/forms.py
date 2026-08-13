from django import forms

from core.models import Banner, ContentPage, RoutineStep, SocialGalleryImage, StoreSettings
from orders.models import Coupon, Order, ShippingZone
from products.models import Category, Product
from core.image_utils import optimize_uploaded_image


class StyledModelForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            if not isinstance(field.widget, forms.CheckboxInput):
                field.widget.attrs.setdefault("class", "form-control")

    def clean(self):
        cleaned = super().clean()
        for name, value in list(cleaned.items()):
            if name in {"image", "main_image", "logo", "favicon"} and value:
                cleaned[name] = optimize_uploaded_image(value)
        return cleaned


class ProductForm(StyledModelForm):
    class Meta:
        model = Product
        fields = [
            "name", "slug", "sku", "category", "short_description", "description",
            "price", "old_price", "stock_quantity", "main_image", "ingredients", "usage",
            "is_active", "is_featured", "is_best_seller", "is_new", "meta_title", "meta_description",
        ]
        widgets = {
            "description": forms.Textarea(attrs={"rows": 5}),
            "ingredients": forms.Textarea(attrs={"rows": 4}),
            "usage": forms.Textarea(attrs={"rows": 4}),
            "main_image": forms.ClearableFileInput(attrs={"accept": "image/jpeg,image/png,image/webp"}),
        }


class CategoryForm(StyledModelForm):
    class Meta:
        model = Category
        fields = ["name", "slug", "image", "description", "is_active", "order"]
        widgets = {"description": forms.Textarea(attrs={"rows": 4})}


class ShippingZoneForm(StyledModelForm):
    class Meta:
        model = ShippingZone
        fields = ["name", "shipping_cost", "is_active", "order"]


class CouponForm(StyledModelForm):
    class Meta:
        model = Coupon
        fields = [
            "code", "discount_type", "value", "minimum_order", "start_date",
            "end_date", "usage_limit", "is_active",
        ]
        widgets = {
            "start_date": forms.DateTimeInput(attrs={"type": "datetime-local"}, format="%Y-%m-%dT%H:%M"),
            "end_date": forms.DateTimeInput(attrs={"type": "datetime-local"}, format="%Y-%m-%dT%H:%M"),
        }


class BannerForm(StyledModelForm):
    class Meta:
        model = Banner
        fields = ["position", "title", "subtitle", "button_text", "button_url", "image", "is_active", "order"]


class ContentPageForm(StyledModelForm):
    class Meta:
        model = ContentPage
        fields = ["title", "slug", "content", "meta_title", "meta_description", "is_active"]
        widgets = {"content": forms.Textarea(attrs={"rows": 12})}


class StoreSettingsForm(StyledModelForm):
    class Meta:
        model = StoreSettings
        exclude = ["created_at", "updated_at"]


class SocialGalleryForm(StyledModelForm):
    class Meta:
        model = SocialGalleryImage
        fields = ["image", "alt_text", "link", "is_active", "order"]


class RoutineStepForm(StyledModelForm):
    class Meta:
        model = RoutineStep
        fields = ["title", "description", "image", "category", "product", "order", "is_active"]


class OrderUpdateForm(StyledModelForm):
    class Meta:
        model = Order
        fields = ["status", "payment_status", "payment_note"]
        widgets = {"payment_note": forms.Textarea(attrs={"rows": 3})}
