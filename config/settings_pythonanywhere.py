"""Production settings tailored for a PythonAnywhere WSGI web app.

The public static/media mappings are configured from PythonAnywhere's Web tab.
Private customer uploads must never be added to those mappings.
"""

import os
from pathlib import Path

from django.core.exceptions import ImproperlyConfigured

from .settings_production import *  # noqa: F401,F403


DEBUG = False

PUBLIC_PROXY_HOST = os.getenv(
    "PUBLIC_PROXY_HOST", "aura.ahmedalghary1.workers.dev"
).strip().lower()

PYTHONANYWHERE_USERNAME = os.getenv("PYTHONANYWHERE_USERNAME", "").strip()
if PYTHONANYWHERE_USERNAME:
    pythonanywhere_host = f"{PYTHONANYWHERE_USERNAME}.pythonanywhere.com".lower()
    if pythonanywhere_host not in ALLOWED_HOSTS:
        ALLOWED_HOSTS.append(pythonanywhere_host)
    pythonanywhere_origin = f"https://{pythonanywhere_host}"
    if pythonanywhere_origin not in CSRF_TRUSTED_ORIGINS:
        CSRF_TRUSTED_ORIGINS.append(pythonanywhere_origin)

if PUBLIC_PROXY_HOST:
    if PUBLIC_PROXY_HOST not in ALLOWED_HOSTS:
        ALLOWED_HOSTS.append(PUBLIC_PROXY_HOST)
    public_proxy_origin = f"https://{PUBLIC_PROXY_HOST}"
    if public_proxy_origin not in CSRF_TRUSTED_ORIGINS:
        CSRF_TRUSTED_ORIGINS.append(public_proxy_origin)

if not any(host.endswith(".pythonanywhere.com") for host in ALLOWED_HOSTS):
    raise ImproperlyConfigured(
        "Set PYTHONANYWHERE_USERNAME or add your *.pythonanywhere.com domain "
        "to ALLOWED_HOSTS."
    )

# Keep mutable application data outside the Git checkout.  This prevents a
# deploy, branch switch, or accidental repository cleanup from replacing the
# live SQLite database.
DEFAULT_DATA_ROOT = BASE_DIR.parent / "cosmetics_data"
DATA_ROOT = Path(
    os.getenv("PYTHONANYWHERE_DATA_ROOT", DEFAULT_DATA_ROOT)
).expanduser().resolve()
STATIC_ROOT = Path(os.getenv("STATIC_ROOT", BASE_DIR / "staticfiles")).expanduser().resolve()
MEDIA_ROOT = Path(os.getenv("MEDIA_ROOT", BASE_DIR / "media")).expanduser().resolve()
PRIVATE_MEDIA_ROOT = Path(
    os.getenv("PRIVATE_MEDIA_ROOT", BASE_DIR / "private_media")
).expanduser().resolve()

SQLITE_PATH = Path(os.getenv("SQLITE_PATH", DATA_ROOT / "db.sqlite3")).expanduser().resolve()
if SQLITE_PATH == BASE_DIR or BASE_DIR in SQLITE_PATH.parents:
    raise ImproperlyConfigured(
        "SQLITE_PATH must be outside the Git project directory on PythonAnywhere. "
        f"Use {DEFAULT_DATA_ROOT / 'db.sqlite3'} (recommended)."
    )
DATABASES["default"]["NAME"] = SQLITE_PATH
DATABASES["default"]["CONN_MAX_AGE"] = 0

# A free PythonAnywhere account has one web worker.  A file cache keeps rate
# limits across worker reloads without introducing a second database service.
CACHES = {
    "default": {
        "BACKEND": os.getenv(
            "CACHE_BACKEND", "django.core.cache.backends.filebased.FileBasedCache"
        ),
        "LOCATION": os.getenv("CACHE_LOCATION", str(DATA_ROOT / "cache")),
        "TIMEOUT": 300,
        "OPTIONS": {"MAX_ENTRIES": 1000},
    }
}

STATIC_URL = "/static/"
MEDIA_URL = "/media/"
FILE_UPLOAD_PERMISSIONS = 0o644
FILE_UPLOAD_DIRECTORY_PERMISSIONS = 0o755

SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_SSL_REDIRECT = env_bool("SECURE_SSL_REDIRECT", True) and not TESTING
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_SAMESITE = "Lax"
SECURE_HSTS_SECONDS = int(os.getenv("SECURE_HSTS_SECONDS", "3600"))
SECURE_HSTS_INCLUDE_SUBDOMAINS = env_bool("SECURE_HSTS_INCLUDE_SUBDOMAINS", False)
SECURE_HSTS_PRELOAD = env_bool("SECURE_HSTS_PRELOAD", False)

# We intentionally cannot preload or control every subdomain of the shared
# pythonanywhere.com parent domain.  Keep the two corresponding deploy checks
# explicit instead of enabling misleading HSTS directives for a domain we do
# not own.
SILENCED_SYSTEM_CHECKS = [
    *globals().get("SILENCED_SYSTEM_CHECKS", []),
    "security.W005",
    "security.W021",
]

EMAIL_TIMEOUT = int(os.getenv("EMAIL_TIMEOUT", "10"))

# PythonAnywhere exposes stdout/stderr in the Web tab error log.  Do not write
# application logs to the small persistent disk on the free plan.
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "standard": {
            "format": "{levelname} {asctime} {name}: {message}",
            "style": "{",
        }
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "standard",
        }
    },
    "root": {
        "handlers": ["console"],
        "level": "CRITICAL" if TESTING else os.getenv("LOG_LEVEL", "WARNING"),
    },
    "loggers": {
        "django": {
            "handlers": ["console"],
            "level": "CRITICAL" if TESTING else "WARNING",
            "propagate": False,
        },
        "orders": {
            "handlers": ["console"],
            "level": "CRITICAL" if TESTING else "INFO",
            "propagate": False,
        },
    },
}
