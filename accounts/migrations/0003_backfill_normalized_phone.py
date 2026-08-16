from django.db import migrations


def backfill_normalized_phones(apps, schema_editor):
    Profile = apps.get_model("accounts", "Profile")
    used = set()
    for profile in Profile.objects.exclude(phone="").order_by("id"):
        digits = "".join(character for character in profile.phone if character.isdigit())
        if digits.startswith("20") and len(digits) == 12:
            digits = f"0{digits[2:]}"
        if digits and digits not in used:
            profile.normalized_phone = digits
            profile.save(update_fields=["normalized_phone"])
            used.add(digits)


class Migration(migrations.Migration):
    dependencies = [("accounts", "0002_profile_normalized_phone")]
    operations = [migrations.RunPython(backfill_normalized_phones, migrations.RunPython.noop)]
