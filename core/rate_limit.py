from functools import wraps
from hashlib import sha256

from django.core.cache import cache
from django.http import JsonResponse
from django.shortcuts import render


def _identity(request):
    if getattr(request, "user", None) and request.user.is_authenticated:
        return f"user:{request.user.pk}"
    return f"ip:{request.META.get('REMOTE_ADDR', 'unknown')}"


def rate_limit(prefix, *, limit, window, methods=("POST",)):
    """Cache-backed limiter; the cache backend can later be moved to Redis."""

    def decorator(view_func):
        @wraps(view_func)
        def wrapped(request, *args, **kwargs):
            if request.method not in methods:
                return view_func(request, *args, **kwargs)
            digest = sha256(f"{prefix}:{_identity(request)}".encode()).hexdigest()
            key = f"rate-limit:{digest}"
            if cache.add(key, 1, timeout=window):
                count = 1
            else:
                try:
                    count = cache.incr(key)
                except ValueError:
                    cache.set(key, 1, timeout=window)
                    count = 1
            if count > limit:
                if request.headers.get("x-requested-with") == "XMLHttpRequest":
                    return JsonResponse(
                        {"message": "محاولات كثيرة. انتظر قليلًا ثم حاول مرة أخرى."}, status=429
                    )
                return render(request, "429.html", status=429)
            return view_func(request, *args, **kwargs)

        return wrapped

    return decorator
