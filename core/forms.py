import re

from django import forms

from .models import ContactMessage


class ContactForm(forms.ModelForm):
    class Meta:
        model = ContactMessage
        fields = ["name", "phone", "email", "subject", "message"]
        widgets = {"message": forms.Textarea(attrs={"rows": 5})}

    def clean_phone(self):
        phone = self.cleaned_data["phone"].strip()
        if not re.fullmatch(r"[0-9+\-\s]{8,20}", phone):
            raise forms.ValidationError("يرجى إدخال رقم هاتف صحيح.")
        return phone
