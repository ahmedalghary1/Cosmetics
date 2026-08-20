from django.db import migrations, models


def enable_configured_instapay(apps, schema_editor):
    StoreSettings = apps.get_model("core", "StoreSettings")
    StoreSettings.objects.exclude(instapay_account_name="").exclude(
        instapay_address=""
    ).update(instapay_enabled=True)


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0003_storesettings_instapay_enabled_and_more"),
    ]

    operations = [
        migrations.RunPython(enable_configured_instapay, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="storesettings",
            name="instapay_enabled",
            field=models.BooleanField(
                default=True,
                verbose_name="تفعيل الدفع عبر InstaPay",
            ),
        ),
    ]
