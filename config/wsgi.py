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
    "Ahmedalgohary1.pythonanywhere.com"
)

os.environ["CSRF_TRUSTED_ORIGINS"] = (
    "https://Ahmedalgohary1.pythonanywhere.com"
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