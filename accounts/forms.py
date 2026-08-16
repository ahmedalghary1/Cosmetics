import re

from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import AuthenticationForm, PasswordChangeForm, UserCreationForm
from django.db import transaction

from .models import Profile, normalize_phone


class ArabicAuthenticationForm(AuthenticationForm):
    username = forms.CharField(label="رقم الهاتف أو اسم المستخدم")
    password = forms.CharField(label="كلمة المرور", strip=False, widget=forms.PasswordInput)
    error_messages = {"invalid_login": "بيانات الدخول غير صحيحة. حاول مرة أخرى.", "inactive": "هذا الحساب غير نشط."}


class RegistrationForm(UserCreationForm):
    full_name = forms.CharField(label="الاسم بالكامل", max_length=150)
    phone = forms.CharField(label="رقم الهاتف", max_length=20)
    email = forms.EmailField(label="البريد الإلكتروني", required=False)

    class Meta:
        model = get_user_model()
        fields = ["full_name", "phone", "email", "password1", "password2"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["password1"].label = "كلمة المرور"
        self.fields["password2"].label = "تأكيد كلمة المرور"
        for field in self.fields.values():
            field.widget.attrs.setdefault("class", "form-control")

    def clean_phone(self):
        phone = self.cleaned_data["phone"].strip()
        if not re.fullmatch(r"[0-9+\-\s]{8,20}", phone):
            raise forms.ValidationError("يرجى إدخال رقم هاتف صحيح.")
        normalized = normalize_phone(phone)
        if (
            Profile.objects.filter(normalized_phone=normalized).exists()
            or get_user_model().objects.filter(username=normalized).exists()
        ):
            raise forms.ValidationError("يوجد حساب مسجل بهذا الرقم بالفعل.")
        return phone

    def clean_email(self):
        email = self.cleaned_data.get("email", "").strip().lower()
        if email and get_user_model().objects.filter(email__iexact=email).exists():
            raise forms.ValidationError("يوجد حساب مسجل بهذا البريد بالفعل.")
        return email

    def save(self, commit=True):
        user = super().save(commit=False)
        full_name = self.cleaned_data["full_name"].strip().split(maxsplit=1)
        user.first_name = full_name[0]
        user.last_name = full_name[1] if len(full_name) > 1 else ""
        user.username = normalize_phone(self.cleaned_data["phone"])
        user.email = self.cleaned_data.get("email", "")
        if commit:
            with transaction.atomic():
                user.save()
                user.profile.phone = self.cleaned_data["phone"]
                user.profile.save()
        return user


class ProfileForm(forms.Form):
    full_name = forms.CharField(label="الاسم بالكامل", max_length=150)
    phone = forms.CharField(label="رقم الهاتف", max_length=20)
    email = forms.EmailField(label="البريد الإلكتروني", required=False)

    def __init__(self, *args, user=None, **kwargs):
        self.user = user
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs.setdefault("class", "form-control")

    def clean_phone(self):
        phone = self.cleaned_data["phone"].strip()
        if not re.fullmatch(r"[0-9+\-\s]{8,20}", phone):
            raise forms.ValidationError("يرجى إدخال رقم هاتف صحيح.")
        normalized = normalize_phone(phone)
        existing = Profile.objects.filter(normalized_phone=normalized).exclude(user=self.user)
        if existing.exists():
            raise forms.ValidationError("يوجد حساب مسجل بهذا الرقم بالفعل.")
        profile = getattr(self.user, "profile", None)
        if (
            profile
            and self.user.username == profile.normalized_phone
            and get_user_model().objects.filter(username=normalized).exclude(pk=self.user.pk).exists()
        ):
            raise forms.ValidationError("رقم الدخول الجديد مستخدم بالفعل.")
        return phone

    def clean_email(self):
        email = self.cleaned_data.get("email", "").strip().lower()
        if email and get_user_model().objects.filter(email__iexact=email).exclude(pk=self.user.pk).exists():
            raise forms.ValidationError("يوجد حساب مسجل بهذا البريد بالفعل.")
        return email

    def save(self):
        parts = self.cleaned_data["full_name"].strip().split(maxsplit=1)
        with transaction.atomic():
            profile, _ = Profile.objects.get_or_create(user=self.user)
            old_normalized = profile.normalized_phone
            new_normalized = normalize_phone(self.cleaned_data["phone"])
            self.user.first_name = parts[0]
            self.user.last_name = parts[1] if len(parts) > 1 else ""
            self.user.email = self.cleaned_data.get("email", "")
            update_fields = ["first_name", "last_name", "email"]
            if self.user.username == old_normalized and self.user.username != new_normalized:
                if get_user_model().objects.filter(username=new_normalized).exclude(pk=self.user.pk).exists():
                    raise forms.ValidationError("تعذر تحديث رقم الدخول لتعارضه مع حساب آخر.")
                self.user.username = new_normalized
                update_fields.append("username")
            self.user.save(update_fields=update_fields)
            profile.phone = self.cleaned_data["phone"]
            profile.save()


class ArabicPasswordChangeForm(PasswordChangeForm):
    old_password = forms.CharField(label="كلمة المرور الحالية", widget=forms.PasswordInput)
    new_password1 = forms.CharField(label="كلمة المرور الجديدة", widget=forms.PasswordInput)
    new_password2 = forms.CharField(label="تأكيد كلمة المرور الجديدة", widget=forms.PasswordInput)
