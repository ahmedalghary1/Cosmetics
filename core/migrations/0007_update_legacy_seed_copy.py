from django.db import migrations


def update_legacy_seed_copy(apps, schema_editor):
    ContentPage = apps.get_model("core", "ContentPage")
    replacements = {
        "الأسئلة-الشائعة": (
            "هل يمكن الدفع عند الاستلام؟ نعم.\n\nهل يتوفر InstaPay؟ نعم، يتم رفع صورة التحويل ثم مراجعتها يدويًا.\n\nكيف أعرف تكلفة الشحن؟ اختاري محافظتك في صفحة إتمام الطلب.",
            "هل يمكن الدفع عند الاستلام؟ نعم.\n\nهل يتوفر InstaPay؟ نعم، يتم رفع صورة التحويل ثم مراجعتها يدويًا.\n\nكيف تظهر تكلفة الشحن؟ تظهر بعد اختيار المحافظة في صفحة إتمام الطلب.",
        ),
        "سياسة-الخصوصية": (
            "نستخدم بياناتك فقط لتنفيذ طلبك وتحسين تجربتك، ولا نبيع بيانات العملاء لأي جهة. نحافظ على البيانات وفق الممارسات الأمنية المناسبة.",
            "نستخدم البيانات فقط لتنفيذ الطلبات وتحسين تجربة المتجر، ولا نبيع بيانات العملاء لأي جهة. نحافظ على البيانات وفق الممارسات الأمنية المناسبة.",
        ),
        "الشروط-والأحكام": (
            "باستخدام المتجر توافقين على تقديم بيانات صحيحة عند الطلب، وعلى سياسات الشحن والاستبدال الموضحة. الأسعار والمخزون يخضعان للتحديث.",
            "يعني استخدام المتجر الموافقة على تقديم بيانات صحيحة عند الطلب، وعلى سياسات الشحن والاستبدال الموضحة. الأسعار والمخزون يخضعان للتحديث.",
        ),
    }
    for slug, (old_content, new_content) in replacements.items():
        ContentPage.objects.filter(slug=slug, content=old_content).update(content=new_content)


class Migration(migrations.Migration):
    dependencies = [("core", "0006_neutral_store_language")]

    operations = [
        migrations.RunPython(update_legacy_seed_copy, migrations.RunPython.noop),
    ]
