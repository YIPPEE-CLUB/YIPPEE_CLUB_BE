from pathlib import Path
import warnings

from django.conf import settings
from django.core.exceptions import ValidationError


def validate_pdf(value):
    if value.size > settings.ACTIVITY_PDF_MAX_BYTES:
        raise ValidationError("PDF 업로드 용량 제한을 초과했습니다.")
    was_closed = value.closed
    if was_closed:
        value.open("rb")
    position = value.tell()
    try:
        value.seek(0)
        header = value.read(8)
        value.seek(max(0, value.size - 1024))
        trailer = value.read()
        if (Path(value.name).suffix.lower() != ".pdf" or
                not header.startswith(b"%PDF-") or b"%%EOF" not in trailer):
            raise ValidationError("올바른 PDF 파일을 업로드해 주세요.")
    finally:
        if was_closed:
            value.close()
        else:
            value.seek(position)


def validate_cover(value):
    from PIL import Image, UnidentifiedImageError

    if value.size > settings.ACTIVITY_IMAGE_MAX_BYTES:
        raise ValidationError("표지 이미지 업로드 용량 제한을 초과했습니다.")
    was_closed = value.closed
    if was_closed:
        value.open("rb")
    position = value.tell()
    try:
        value.seek(0)
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(value) as image:
                extensions = {"PNG": {".png"}, "JPEG": {".jpg", ".jpeg"}, "WEBP": {".webp"}}
                if Path(value.name).suffix.lower() not in extensions.get(image.format, set()):
                    raise ValidationError("PNG, JPEG, WEBP 이미지만 허용됩니다.")
                image.verify()
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError,
            Image.DecompressionBombWarning) as error:
        raise ValidationError("올바른 이미지 파일을 업로드해 주세요.") from error
    finally:
        if was_closed:
            value.close()
        else:
            value.seek(position)
