from .settings import *  # noqa: F401,F403

DEBUG = False
SECRET_KEY = os.getenv("DJANGO_SECRET_KEY", "&67pl5&8f0t^i88%03zzj^qe#xkpgk@kt-t$z29+-1i^6#kpr2").strip()
if not SECRET_KEY:
    raise ImproperlyConfigured("DJANGO_SECRET_KEY is required by production settings.")
STORAGES["staticfiles"] = {
    "BACKEND": (
        "django.contrib.staticfiles.storage.StaticFilesStorage"
        if TESTING
        else "whitenoise.storage.CompressedManifestStaticFilesStorage"
    )
}
if not EMAIL_CONFIGURED:
    raise ImproperlyConfigured("EMAIL_HOST_USER and EMAIL_HOST_PASSWORD are required in production.")
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_SSL_REDIRECT = env_bool("SECURE_SSL_REDIRECT", True)
SECURE_HSTS_SECONDS = int(os.getenv("SECURE_HSTS_SECONDS", "3600"))
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = env_bool("SECURE_HSTS_PRELOAD", True)
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = "DENY"
