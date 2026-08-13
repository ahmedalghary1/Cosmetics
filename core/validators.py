from pathlib import Path

from django.core.exceptions import ValidationError


ALLOWED_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}
MAX_IMAGE_SIZE = 5 * 1024 * 1024


def validate_image_upload(file):
    extension = Path(file.name).suffix.lower()
    if extension not in ALLOWED_IMAGE_EXTENSIONS:
        raise ValidationError("صيغة الصورة غير مدعومة. استخدم JPG أو PNG أو WEBP.")
    if file.size > MAX_IMAGE_SIZE:
        raise ValidationError("حجم الصورة يجب ألا يزيد عن 5 ميجابايت.")
    try:
        from PIL import Image

        image = Image.open(file)
        image.verify()
        file.seek(0)
    except Exception as exc:
        raise ValidationError("الملف المرفوع ليس صورة صالحة.") from exc
