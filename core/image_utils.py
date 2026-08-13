from io import BytesIO
from pathlib import Path

from django.core.files.base import ContentFile
from django.core.files.uploadedfile import UploadedFile
from PIL import Image, ImageOps


def optimize_uploaded_image(file, max_dimension=1800, quality=84):
    """Resize an uploaded catalog image and return a lightweight WebP file."""
    if not isinstance(file, UploadedFile):
        return file
    file.seek(0)
    image = Image.open(file)
    image = ImageOps.exif_transpose(image)
    if image.mode not in {"RGB", "RGBA"}:
        image = image.convert("RGBA" if "transparency" in image.info else "RGB")
    image.thumbnail((max_dimension, max_dimension), Image.Resampling.LANCZOS)
    output = BytesIO()
    image.save(output, format="WEBP", quality=quality, method=6)
    stem = Path(file.name).stem[:80] or "image"
    return ContentFile(output.getvalue(), name=f"{stem}.webp")
