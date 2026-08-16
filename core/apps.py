from django.apps import AppConfig


class CoreConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "core"
    verbose_name = "المحتوى والإعدادات"

    def ready(self):
        from . import sqlite  # noqa: F401
