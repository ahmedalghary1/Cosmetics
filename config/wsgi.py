import os
import sys

# =========================================================
# Project path
# =========================================================
PROJECT_PATH = "/home/Ahmedalgohary1/Cosmetics"

if PROJECT_PATH not in sys.path:
    sys.path.insert(0, PROJECT_PATH)


# =========================================================
# Django production settings
# =========================================================
os.environ["DEBUG"] = "False"

os.environ["ALLOWED_HOSTS"] = (
    "ahmedalgohary1.pythonanywhere.com,"
    "aura.ahmedalghary1.workers.dev"
)

os.environ["CSRF_TRUSTED_ORIGINS"] = (
    "https://ahmedalgohary1.pythonanywhere.com,"
    "https://aura.ahmedalghary1.workers.dev"
)


# =========================================================
# Secret Key
# مهم: استبدل القيمة دي بمفتاح سري قوي خاص بك
# =========================================================
os.environ["DJANGO_SECRET_KEY"] = (
    "CHANGE-THIS-TO-A-LONG-RANDOM-SECRET-KEY"
)


# =========================================================
# Django settings module
# =========================================================
os.environ["DJANGO_SETTINGS_MODULE"] = "config.settings"


# =========================================================
# Start Django
# =========================================================
from django.core.wsgi import get_wsgi_application

application = get_wsgi_application()
