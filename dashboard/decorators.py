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
