from django import forms

from .models import Category


class ProductFilterForm(forms.Form):
    SORT_OPTIONS = [
        ("newest", "الأحدث"),
        ("price_asc", "السعر: الأقل أولًا"),
        ("price_desc", "السعر: الأعلى أولًا"),
        ("best", "الأكثر مبيعًا"),
    ]

    q = forms.CharField(required=False, max_length=180)
    category = forms.SlugField(required=False, allow_unicode=True)
    min_price = forms.DecimalField(required=False, min_value=0, max_digits=10, decimal_places=2)
    max_price = forms.DecimalField(required=False, min_value=0, max_digits=10, decimal_places=2)
    in_stock = forms.BooleanField(required=False)
    offers = forms.BooleanField(required=False)
    best = forms.BooleanField(required=False)
    new = forms.BooleanField(required=False)
    sort = forms.ChoiceField(required=False, choices=SORT_OPTIONS)

    def clean_category(self):
        slug = self.cleaned_data.get("category", "")
        if slug and not Category.objects.filter(slug=slug, is_active=True).exists():
            raise forms.ValidationError("التصنيف المحدد غير متاح.")
        return slug

    def clean(self):
        cleaned = super().clean()
        minimum = cleaned.get("min_price")
        maximum = cleaned.get("max_price")
        if minimum is not None and maximum is not None and minimum > maximum:
            self.add_error("max_price", "يجب أن يكون الحد الأعلى أكبر من أو مساويًا للحد الأدنى.")
        return cleaned
