from functools import wraps

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied


def staff_required(view_func):
    @login_required(login_url="accounts:login")
    @wraps(view_func)
    def wrapped(request, *args, **kwargs):
        if not request.user.is_staff or not request.user.is_active:
            raise PermissionDenied
        return view_func(request, *args, **kwargs)

    return wrapped


def dashboard_permission(*permissions):
    """Require dashboard access plus every declared Django permission."""

    def decorator(view_func):
        @login_required(login_url="accounts:login")
        @wraps(view_func)
        def wrapped(request, *args, **kwargs):
            user = request.user
            if not user.is_active or not user.is_staff:
                raise PermissionDenied
            if not user.is_superuser and not user.has_perms(permissions):
                raise PermissionDenied
            return view_func(request, *args, **kwargs)

        return wrapped

    return decorator
