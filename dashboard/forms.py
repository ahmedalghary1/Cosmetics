from django import forms
from django.forms import inlineformset_factory
from django.contrib.auth import get_user_model

from core.models import Banner, ContentPage, Offer, RoutineStep, SocialGalleryImage, StoreSettings
from orders.models import Coupon, Order, ReturnRequest, ShippingZone
from products.models import BundleItem, Category, InventoryBatch, Product, ProductVariant, VariantOption
from core.image_utils import optimize_uploaded_image


class StyledModelForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            if not isinstance(field.widget, (forms.CheckboxInput, forms.CheckboxSelectMultiple)):
                field.widget.attrs.setdefault("class", "form-control")

    def clean(self):
        cleaned = super().clean()
        for name, value in list(cleaned.items()):
            if name in {"image", "main_image", "logo", "favicon"} and value:
                cleaned[name] = optimize_uploaded_image(value)
        return cleaned


class OfferProductChoiceField(forms.ModelMultipleChoiceField):
    def label_from_instance(self, product):
        category_name = product.category.name if product.category_id else "بدون قسم"
        return f"{product.name} — {product.sku} — {category_name}"


class ProductForm(StyledModelForm):
    class Meta:
        model = Product
        fields = [
            "name", "slug", "sku", "categories", "short_description", "description",
            "price", "stock_quantity", "has_variants", "main_image", "ingredients", "usage",
            "brand", "country_of_origin", "key_ingredients", "benefits", "warnings",
            "suitable_for", "skin_types", "hair_types", "size_label", "pao_months",
            "cruelty_free", "vegan",
            "is_active", "is_featured", "is_best_seller", "is_new", "meta_title", "meta_description",
        ]
        widgets = {
            "description": forms.Textarea(attrs={"rows": 5}),
            "ingredients": forms.Textarea(attrs={"rows": 4}),
            "usage": forms.Textarea(attrs={"rows": 4}),
            "main_image": forms.ClearableFileInput(attrs={"accept": "image/jpeg,image/png,image/webp"}),
            "categories": forms.CheckboxSelectMultiple(attrs={"data-choice-picker-options": ""}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["categories"].required = True
        self.fields["categories"].help_text = "اختاري قسمًا واحدًا أو أكثر لعرض المنتج داخلها."

    def clean(self):
        cleaned = super().clean()
        categories = cleaned.get("categories")
        if categories:
            self.instance.category = categories[0]
        if not self.instance.pk:
            self.instance.is_bundle = False
        return cleaned


class BundleItemForm(StyledModelForm):
    class Meta:
        model = BundleItem
        fields = ["product", "variant", "quantity"]

    def __init__(self, *args, bundle=None, **kwargs):
        super().__init__(*args, **kwargs)
        products = Product.objects.filter(is_bundle=False).select_related("category").order_by("name")
        if bundle and bundle.pk:
            products = products.exclude(pk=bundle.pk)
        self.fields["product"].queryset = products
        self.fields["variant"].queryset = ProductVariant.objects.filter(
            is_active=True, product__is_bundle=False,
        ).select_related("product").order_by("product__name", "option_summary")
        self.fields["variant"].help_text = "يُحدد فقط إذا كان المنتج له نوع/حجم؛ وإلا يُترك فارغًا."


class BaseBundleItemFormSet(forms.BaseInlineFormSet):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for form in self.forms:
            form.fields["product"].queryset = Product.objects.filter(
                is_bundle=False,
            ).exclude(pk=self.instance.pk).select_related("category").order_by("name")

    def clean(self):
        super().clean()
        if any(self.errors) or not getattr(self.instance, "is_bundle", False):
            return
        active_forms = [
            form for form in self.forms
            if form.cleaned_data and not form.cleaned_data.get("DELETE") and form.cleaned_data.get("product")
        ]
        if not active_forms:
            raise forms.ValidationError("أضيفي منتجًا واحدًا على الأقل داخل الباقة.")


BundleItemFormSet = inlineformset_factory(
    Product,
    BundleItem,
    fk_name="bundle",
    form=BundleItemForm,
    formset=BaseBundleItemFormSet,
    extra=3,
    can_delete=True,
)


class CategoryForm(StyledModelForm):
    class Meta:
        model = Category
        fields = ["name", "slug", "image", "description", "is_active", "order"]
        widgets = {"description": forms.Textarea(attrs={"rows": 4})}


class ShippingZoneForm(StyledModelForm):
    class Meta:
        model = ShippingZone
        fields = [
            "name", "shipping_cost", "estimated_delivery_min_days",
            "estimated_delivery_max_days", "is_active", "order",
        ]


class CouponForm(StyledModelForm):
    class Meta:
        model = Coupon
        fields = [
            "code", "discount_type", "value", "minimum_order", "start_date",
            "end_date", "usage_limit", "is_active",
            "max_uses_per_customer", "products", "categories",
        ]
        widgets = {
            "start_date": forms.DateTimeInput(attrs={"type": "datetime-local"}, format="%Y-%m-%dT%H:%M"),
            "end_date": forms.DateTimeInput(attrs={"type": "datetime-local"}, format="%Y-%m-%dT%H:%M"),
            "products": forms.SelectMultiple(attrs={"size": 8}),
            "categories": forms.SelectMultiple(attrs={"size": 6}),
        }


class ProductVariantForm(StyledModelForm):
    class Meta:
        model = ProductVariant
        fields = [
            "sku", "options", "option_summary", "price", "old_price",
            "stock_quantity", "barcode", "weight_grams", "is_active",
        ]
        widgets = {"options": forms.SelectMultiple(attrs={"size": 7})}


class VariantOptionForm(StyledModelForm):
    class Meta:
        model = VariantOption
        fields = ["option_type", "value", "order"]


class InventoryBatchForm(StyledModelForm):
    class Meta:
        model = InventoryBatch
        fields = [
            "product", "variant", "batch_number", "quantity", "manufacturing_date",
            "expiry_date", "received_date", "purchase_cost", "is_active",
        ]
        widgets = {
            "manufacturing_date": forms.DateInput(attrs={"type": "date"}),
            "expiry_date": forms.DateInput(attrs={"type": "date"}),
            "received_date": forms.DateInput(attrs={"type": "date"}),
        }

    def clean(self):
        cleaned = super().clean()
        product = cleaned.get("product")
        variant = cleaned.get("variant")
        if variant and product and variant.product_id != product.pk:
            self.add_error("variant", "الخيار لا يتبع المنتج المحدد.")
        return cleaned


class BannerForm(StyledModelForm):
    class Meta:
        model = Banner
        fields = ["position", "title", "subtitle", "button_text", "button_url", "image", "is_active", "order"]


class OfferForm(StyledModelForm):
    products = OfferProductChoiceField(
        label="المنتجات",
        queryset=Product.objects.none(),
        widget=forms.CheckboxSelectMultiple(attrs={"data-choice-picker-options": ""}),
    )

    class Meta:
        model = Offer
        fields = [
            "eyebrow", "title", "subtitle", "sell_as_bundle", "image",
            "bundle_price", "bundle_old_price", "products", "button_text", "button_url",
            "starts_at", "ends_at", "is_active", "order",
        ]
        widgets = {
            "image": forms.ClearableFileInput(attrs={"accept": "image/jpeg,image/png,image/webp"}),
            "starts_at": forms.DateTimeInput(attrs={"type": "datetime-local"}, format="%Y-%m-%dT%H:%M"),
            "ends_at": forms.DateTimeInput(attrs={"type": "datetime-local"}, format="%Y-%m-%dT%H:%M"),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["products"].queryset = Product.objects.filter(
            is_active=True, is_bundle=False, has_variants=False,
        ).select_related("category").prefetch_related("categories").order_by("name")
        self.fields["products"].help_text = "اضغطي على المنتجات المطلوبة مباشرة، ويمكنك البحث والتحديد باللمس من الهاتف."
        if not self.instance.pk:
            self.initial.setdefault("sell_as_bundle", True)

    def clean_products(self):
        products = self.cleaned_data["products"]
        if self.cleaned_data.get("sell_as_bundle"):
            invalid = [product.name for product in products if product.is_bundle or product.has_variants]
            if invalid:
                raise forms.ValidationError(
                    "منتجات الباقة يجب أن تكون منتجات عادية بلا خيارات: " + "، ".join(invalid)
                )
            return products
        invalid = [product.name for product in products if not product.old_price or product.old_price <= product.price]
        if invalid:
            raise forms.ValidationError(
                "يجب إضافة سعر قديم أعلى من السعر الحالي لهذه المنتجات أولًا: " + "، ".join(invalid)
            )
        return products

    def clean(self):
        cleaned = super().clean()
        if not cleaned.get("sell_as_bundle"):
            return cleaned
        image = cleaned.get("image")
        has_existing_image = image is None and bool(getattr(self.instance, "image", None))
        if not image and not has_existing_image:
            self.add_error("image", "صورة العرض مطلوبة عند بيعه كباقة واحدة.")
        price = cleaned.get("bundle_price")
        products = cleaned.get("products")
        if price is None:
            self.add_error("bundle_price", "أدخلي سعر العرض كاملًا.")
        elif price <= 0:
            self.add_error("bundle_price", "سعر العرض يجب أن يكون أكبر من صفر.")
        if price is not None and products:
            old_price = cleaned.get("bundle_old_price") or sum(product.price for product in products)
            if old_price <= price:
                self.add_error(
                    "bundle_old_price",
                    "السعر قبل العرض أو مجموع أسعار المنتجات يجب أن يكون أكبر من سعر العرض.",
                )
        return cleaned


class ContentPageForm(StyledModelForm):
    REQUIRED_PAGE_SLUGS = {
        "من-نحن", "الشحن-والتوصيل", "الاستبدال-والاسترجاع",
        "الأسئلة-الشائعة", "سياسة-الخصوصية", "الشروط-والأحكام",
    }

    class Meta:
        model = ContentPage
        fields = ["title", "slug", "content", "meta_title", "meta_description", "is_active"]
        widgets = {
            "content": forms.Textarea(attrs={"rows": 12}),
            "meta_description": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["content"].help_text = "محتوى الصفحة كما سيظهر للزوار. يُترك سطر فارغ بين الفقرات."
        self.fields["meta_title"].help_text = "اختياري: عنوان مختصر يظهر في نتائج البحث."
        self.fields["meta_description"].help_text = "اختياري: وصف موجز للصفحة في نتائج البحث."
        if self.instance.pk and self.instance.slug in self.REQUIRED_PAGE_SLUGS:
            self.fields["slug"].disabled = True
            self.fields["slug"].help_text = "رابط صفحة أساسية ومحمي من التغيير حتى تظل روابط الموقع تعمل."


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

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        if user and not user.is_superuser:
            if not user.has_perm("orders.transition_order"):
                self.fields["status"].disabled = True
            if not user.has_perm("orders.verify_payment"):
                self.fields["payment_status"].disabled = True
                self.fields["payment_note"].disabled = True


class ReturnUpdateForm(StyledModelForm):
    class Meta:
        model = ReturnRequest
        fields = ["status", "refund_amount", "admin_note"]
        widgets = {"admin_note": forms.Textarea(attrs={"rows": 4})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.pk:
            for item in self.instance.items.select_related("order_item"):
                self.fields[f"restockable_{item.pk}"] = forms.BooleanField(
                    label=f"صالح للإعادة: {item.order_item.product_name} × {item.quantity}",
                    required=False,
                    initial=item.restockable,
                )

    def clean_refund_amount(self):
        amount = self.cleaned_data["refund_amount"]
        order = self.instance.order
        remaining = order.total - order.refunded_amount
        items_maximum = sum(
            item.order_item.unit_price * item.quantity for item in self.instance.items.select_related("order_item")
        )
        if amount > min(remaining, items_maximum):
            raise forms.ValidationError("مبلغ الرد أكبر من قيمة المنتجات أو المتبقي في الطلب.")
        return amount


class UserRoleForm(StyledModelForm):
    class Meta:
        model = get_user_model()
        fields = ["groups", "is_staff"]
        widgets = {"groups": forms.SelectMultiple(attrs={"size": 7})}
