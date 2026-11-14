"""All-or-nothing import of the eight supplied files; never overwrites records."""
import hashlib
from pathlib import Path

from django.core.files import File
from django.db import connection, transaction
from django.core.management.base import CommandError

from categories.models import Category
from .models import Activity
from .validators import validate_pdf, validate_cover

CATEGORY_NAMES = ("신체운동·건강", "자연탐구")
SAMPLES = (
    ("단비와 보리의 징검다리 모험", "인형을 집까지 안전하게 이동시키며 차례를 번갈아 가며 놀이하는 활동", "easy", 5, "01_징검다리_모험.pdf", "01_징검다리_표지.png"),
    ("단비와 보리의 숫자 놀이", "종이 길을 따라 숫자 카드를 활용하며 결승점에 도착하는 놀이", "hard", 10, "02_숫자_놀이.pdf", "02_숫자_표지.png"),
    ("단비랑 보리의 콩 놀이", "숫자 카드에 맞춰 콩을 떠서 컵에 모으며 수 개념과 소근육 조절 능력을 기르는 활동", "hard", 5, "03_콩_놀이.pdf", "03_콩_표지.png"),
    ("단비와 보리의 공 놀이", "가까운 거리와 먼 거리에서 공을 바구니에 던지며 신체 조절과 의사소통 능력을 기르는 활동", "hard", 15, "04_공_놀이.pdf", "04_공_표지.png"),
)


def sha256(stream):
    result = hashlib.sha256()
    for chunk in iter(lambda: stream.read(1024 * 1024), b""):
        result.update(chunk)
    return result.hexdigest()


def preflight(root):
    root = Path(root).resolve()
    result = {}
    for row in SAMPLES:
        for filename, validator in ((row[4], validate_pdf), (row[5], validate_cover)):
            path = root / filename
            if not path.is_file() or path.resolve().parent != root:
                raise CommandError("필수 자료 파일이 없거나 경로가 올바르지 않습니다: " + filename)
            with path.open("rb") as stream:
                validator(File(stream, name=filename))
                stream.seek(0)
                result[filename] = {"bytes": path.stat().st_size, "sha256": sha256(stream)}
    return result


def sample_categories():
    rows = []
    for name in CATEGORY_NAMES:
        matches = list(Category.objects.filter(name=name))
        if len(matches) != 1 or matches[0].name != name:
            raise CommandError("공통 카테고리 이름을 정확히 한 개씩 준비해 주세요.")
        rows.append(matches[0])
    return rows


def register_private(root, journal=lambda event: None):
    """Record file intents before writes; clean up only this attempt on rollback.

    A hard process/DB outage retains the journal for manual reconciliation.
    A retry refuses any existing Activity instead of duplicating a partial batch.
    """
    sources = preflight(root)
    categories = sample_categories()
    storage = Activity._meta.get_field("pdf").storage
    saved, instances = [], []
    with connection.cursor() as cursor:
        cursor.execute("SELECT GET_LOCK('yippee_sample_activity_import',0)")
        if cursor.fetchone()[0] != 1:
            raise CommandError("다른 활동지 등록 작업이 실행 중입니다.")
    try:
        with transaction.atomic():
            if list(Activity.objects.select_for_update().all()):
                raise CommandError("기존 활동지가 있어 중복 등록하지 않고 중단합니다.")
            for title, description, difficulty, duration, pdf_name, image_name in SAMPLES:
                row = Activity(title=title, description=description, age_min_months=60, age_max_months=65,
                               difficulty=difficulty, duration_min=duration, duration_max=duration,
                               price=0, is_public=False)
                instances.append(row)
                for field_name, filename in (("pdf", pdf_name), ("image", image_name)):
                    field = Activity._meta.get_field(field_name)
                    planned = field.generate_filename(row, filename).replace("\\", "/")
                    if storage.exists(planned):
                        raise CommandError("새 파일 경로 충돌로 중단합니다.")
                    saved.append(planned)
                    journal({"event": "file_intent", "source": filename, "stored": planned})
                    with (Path(root) / filename).open("rb") as stream:
                        actual = storage.save(planned, File(stream, name=filename), max_length=field.max_length)
                    if actual != planned:
                        saved.append(actual)
                    journal({"event": "file_saved", "source": filename, "stored": actual})
                    setattr(row, field_name, actual)
                row.save()
                row.categories.set(categories)
                journal({"event": "row_staged", "id": row.pk, "title": row.title})
            verify_rows(root, [r.pk for r in instances], public=False, expected_sources=sources)
        journal({"event": "committed_private", "ids": [r.pk for r in instances]})
        return [r.pk for r in instances]
    except BaseException:
        for row in instances:
            row.pdf.close()
            row.image.close()
        # If DB state cannot be confirmed, preserve files for journal-led recovery.
        for name in saved:
            from django.db.models import Q
            if not Activity.objects.filter(Q(pdf=name) | Q(image=name)).exists():
                storage.delete(name)
                journal({"event": "rolled_back_file_removed", "stored": name})
        raise
    finally:
        with connection.cursor() as cursor:
            cursor.execute("SELECT RELEASE_LOCK('yippee_sample_activity_import')")


def verify_rows(root, ids, *, public, expected_sources=None):
    sources = expected_sources or preflight(root)
    if len(ids) != 4 or Activity.objects.count() != 4:
        raise CommandError("등록된 활동지 수가 예상과 다릅니다.")
    category_ids = {r.pk for r in sample_categories()}
    result = []
    for pk, sample in zip(ids, SAMPLES):
        row = Activity.objects.get(pk=pk)
        title, description, difficulty, duration, pdf_name, image_name = sample
        actual = (row.title, row.description, row.difficulty, row.duration_min, row.duration_max,
                  row.price, row.age_min_months, row.age_max_months, row.is_public)
        if actual != (title, description, difficulty, duration, duration, 0, 60, 65, public):
            raise CommandError("활동지 메타데이터가 예상과 다릅니다.")
        if set(row.categories.values_list("pk", flat=True)) != category_ids:
            raise CommandError("카테고리 연결이 예상과 다릅니다.")
        for file, filename in ((row.pdf, pdf_name), (row.image, image_name)):
            with file.storage.open(file.name, "rb") as stream:
                if sha256(stream) != sources[filename]["sha256"]:
                    raise CommandError("저장 파일이 원본과 다릅니다.")
        result.append({"id": pk, "title": title, "price": row.price, "age_min_months": 60,
                       "age_max_months": 65, "duration_min": duration, "duration_max": duration,
                       "difficulty": difficulty, "categories": sorted(category_ids), "is_public": public,
                       "pdf": row.pdf.name, "image": row.image.name})
    return result
