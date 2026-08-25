import re

from django import forms
from django.db.models import Sum

from core.models import StoreSettings

from .models import Order, ReturnRequest, ReturnRequestItem, ShippingZone


def validate_phone(value):
    value = value.strip()
    if not re.fullmatch(r"[0-9+\-\s]{8,20}", value):
        raise forms.ValidationError("يرجى إدخال رقم هاتف صحيح.")
    return value


class CheckoutForm(forms.ModelForm):
    terms_accepted = forms.BooleanField(
        label="أوافق على شروط الشراء وسياسة الخصوصية",
        error_messages={"required": "يجب الموافقة على الشروط قبل إتمام الطلب."},
    )

    class Meta:
        model = Order
        fields = [
            "full_name", "email", "phone", "alternative_phone", "governorate", "city",
            "address", "landmark", "notes", "payment_method", "payment_receipt",
        ]
        widgets = {
            "address": forms.Textarea(attrs={"rows": 3}),
            "notes": forms.Textarea(attrs={"rows": 3}),
            "payment_method": forms.RadioSelect,
            "payment_receipt": forms.ClearableFileInput(
                attrs={"accept": "image/jpeg,image/png,image/webp"}
            ),
        }

    def __init__(self, *args, **kwargs):
        self.store_settings = kwargs.pop("store_settings", None) or StoreSettings.load()
        super().__init__(*args, **kwargs)
        self.fields["governorate"].queryset = ShippingZone.objects.filter(is_active=True)
        self.fields["governorate"].empty_label = "— المحافظة —"
        payment_choices = [
            (Order.PaymentMethod.CASH, Order.PaymentMethod.CASH.label),
        ]
        if (
            self.store_settings.instapay_enabled
            and self.store_settings.instapay_account_name.strip()
            and self.store_settings.instapay_address.strip()
        ):
            payment_choices.append(
                (Order.PaymentMethod.INSTAPAY, Order.PaymentMethod.INSTAPAY.label)
            )
        # Model choice fields add an empty option when there is no model default.
        # Checkout always requires a real payment method, so expose only the two
        # methods supported by the store.
        self.fields["payment_method"].choices = payment_choices
        self.fields["payment_method"].initial = Order.PaymentMethod.CASH
        for name, field in self.fields.items():
            if name == "payment_method":
                field.widget.attrs.setdefault("class", "payment-radio")
            elif name != "terms_accepted":
                field.widget.attrs.setdefault("class", "form-control")

    def clean_phone(self):
        return validate_phone(self.cleaned_data["phone"])

    def clean_alternative_phone(self):
        value = self.cleaned_data.get("alternative_phone", "")
        return validate_phone(value) if value else ""

    def clean(self):
        cleaned = super().clean()
        if cleaned.get("payment_method") == Order.PaymentMethod.INSTAPAY and not cleaned.get("payment_receipt"):
            self.add_error("payment_receipt", "رفع صورة التحويل مطلوب عند اختيار الدفع عبر InstaPay.")
        elif cleaned.get("payment_method") != Order.PaymentMethod.INSTAPAY:
            cleaned["payment_receipt"] = None
        return cleaned


class ShippingQuoteForm(forms.Form):
    zone = forms.ModelChoiceField(queryset=ShippingZone.objects.none())

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["zone"].queryset = ShippingZone.objects.filter(is_active=True)


class ReturnRequestForm(forms.ModelForm):
    class Meta:
        model = ReturnRequest
        fields = ["reason", "customer_note"]
        widgets = {"customer_note": forms.Textarea(attrs={"rows": 4})}

    def __init__(self, *args, order, **kwargs):
        self.order = order
        super().__init__(*args, **kwargs)
        for item in order.items.all():
            previously_requested = ReturnRequestItem.objects.filter(
                order_item=item,
            ).exclude(return_request__status=ReturnRequest.Status.REJECTED).aggregate(
                total=Sum("quantity")
            )["total"] or 0
            available = max(item.quantity - previously_requested, 0)
            if available:
                self.fields[f"item_{item.pk}"] = forms.IntegerField(
                    label=f"{item.product_name} {item.variant_name}".strip(),
                    min_value=0,
                    max_value=available,
                    initial=0,
                    required=False,
                )
        for field in self.fields.values():
            field.widget.attrs.setdefault("class", "form-control")

    def clean(self):
        cleaned = super().clean()
        if not any(cleaned.get(name, 0) for name in self.fields if name.startswith("item_")):
            raise forms.ValidationError("يجب تحديد كمية لمنتج واحد على الأقل.")
        return cleaned

    def save(self, user=None):
        request = super().save(commit=False)
        request.order = self.order
        request.user = user
        request.save()
        for name, quantity in self.cleaned_data.items():
            if name.startswith("item_") and quantity:
                ReturnRequestItem.objects.create(
                    return_request=request,
                    order_item_id=int(name.split("_", 1)[1]),
                    quantity=quantity,
                )
        return request
