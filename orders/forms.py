import re

from django import forms

from .models import Order, ShippingZone


def validate_phone(value):
    value = value.strip()
    if not re.fullmatch(r"[0-9+\-\s]{8,20}", value):
        raise forms.ValidationError("يرجى إدخال رقم هاتف صحيح.")
    return value


class CheckoutForm(forms.ModelForm):
    class Meta:
        model = Order
        fields = [
            "full_name", "phone", "alternative_phone", "governorate", "city",
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
        super().__init__(*args, **kwargs)
        self.fields["governorate"].queryset = ShippingZone.objects.filter(is_active=True)
        self.fields["governorate"].empty_label = "اختر المحافظة"
        self.fields["payment_method"].initial = Order.PaymentMethod.CASH
        for field in self.fields.values():
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
