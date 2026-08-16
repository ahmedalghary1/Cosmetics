from django.contrib.auth import get_user_model
from django.contrib.auth.backends import ModelBackend

from .models import Profile, normalize_phone


class PhoneOrUsernameBackend(ModelBackend):
    def authenticate(self, request, username=None, password=None, **kwargs):
        if username is None or password is None:
            return None
        UserModel = get_user_model()
        user = None
        normalized = normalize_phone(username)
        if normalized:
            profile = Profile.objects.select_related("user").filter(normalized_phone=normalized).first()
            user = profile.user if profile else None
        if user is None:
            try:
                user = UserModel._default_manager.get(username__iexact=username.strip())
            except UserModel.DoesNotExist:
                UserModel().set_password(password)
                return None
        if user.check_password(password) and self.user_can_authenticate(user):
            return user
        return None
