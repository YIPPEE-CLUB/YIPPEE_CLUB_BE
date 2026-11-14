from django.conf import settings
from django.core.files.storage import FileSystemStorage, storages
from django.utils.deconstruct import deconstructible
from pathlib import Path
from uuid import uuid4


@deconstructible
class PrivateActivityStorage(FileSystemStorage):
    def __init__(self):
        super().__init__()

    @property
    def base_location(self):
        return str(settings.ACTIVITY_PRIVATE_ROOT)

    @property
    def location(self):
        return str(Path(settings.ACTIVITY_PRIVATE_ROOT).resolve())

    def url(self, name):
        raise ValueError("활동지 파일은 접근 제어 API로만 조회할 수 있습니다.")


def activity_storage():
    return storages["activities"]


def upload_path(instance, filename):
    return "activities/" + uuid4().hex + Path(filename).suffix.lower()
