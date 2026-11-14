from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator, MaxValueValidator
from django.db import models

from .storage import activity_storage, upload_path
from .validators import validate_pdf, validate_cover


class Activity(models.Model):
    class Difficulty(models.TextChoices):
        EASY = "easy", "하"
        HARD = "hard", "상"

    title = models.CharField("제목", max_length=255)
    description = models.TextField("설명")
    age_min_months = models.PositiveSmallIntegerField("최소 월령")
    age_max_months = models.PositiveSmallIntegerField("최대 월령")
    difficulty = models.CharField("난이도", max_length=16, choices=Difficulty.choices)
    duration_min = models.PositiveSmallIntegerField("최소 소요 시간(분)", validators=[MinValueValidator(1)])
    duration_max = models.PositiveSmallIntegerField("최대 소요 시간(분)", validators=[MinValueValidator(1)])
    categories = models.ManyToManyField("categories.Category", through="ActivityCategory", verbose_name="카테고리")
    price = models.PositiveIntegerField("가격", default=0, validators=[MaxValueValidator(0)])
    image = models.FileField("표지 이미지", upload_to=upload_path, storage=activity_storage, validators=[validate_cover])
    pdf = models.FileField("개별 PDF", upload_to=upload_path, storage=activity_storage, validators=[validate_pdf])
    is_public = models.BooleanField("공개 여부", default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "activities"
        ordering = ("-created_at", "-id")
        constraints = [
            models.CheckConstraint(condition=models.Q(price=0), name="activity_price_zero"),
            models.CheckConstraint(condition=models.Q(age_max_months__gte=models.F("age_min_months")), name="activity_age_range"),
            models.CheckConstraint(condition=models.Q(duration_min__gte=1) & models.Q(duration_max__gte=models.F("duration_min")), name="activity_duration_range"),
            models.CheckConstraint(condition=models.Q(difficulty__in=["easy", "hard"]), name="activity_difficulty"),
        ]

    def clean(self):
        super().clean()
        errors = {}
        if self.age_min_months is not None and self.age_max_months is not None and self.age_min_months > self.age_max_months:
            errors["age_max_months"] = "최대 개월 수는 최소 개월 수 이상이어야 합니다."
        if self.duration_min is not None and self.duration_max is not None and self.duration_min > self.duration_max:
            errors["duration_max"] = "최대 소요 시간은 최소 소요 시간 이상이어야 합니다."
        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        self.full_clean(exclude=["categories"])
        return super().save(*args, **kwargs)

    def __str__(self):
        return self.title


class ActivityCategory(models.Model):
    activity = models.ForeignKey(Activity, on_delete=models.CASCADE)
    category = models.ForeignKey("categories.Category", on_delete=models.PROTECT)

    class Meta:
        db_table = "activity_categories"
        constraints = [models.UniqueConstraint(fields=("activity", "category"), name="unique_activity_category")]
