from django import forms
from django.contrib import admin
from categories.models import Category
from .models import Activity


class ActivityForm(forms.ModelForm):
    categories = forms.ModelMultipleChoiceField(queryset=Category.objects.all(), label="카테고리", required=True,
        help_text="기존 카테고리를 선택하세요. 목록이 비어 있으면 카테고리 담당자에게 등록을 요청하세요.")

    class Meta:
        model = Activity
        exclude = ("price",)
        # Avoid storage.url() in ClearableFileInput for private files.
        widgets = {"image": forms.FileInput(), "pdf": forms.FileInput()}
        labels = {
            "age_min_months": "최소 개월 수",
            "age_max_months": "최대 개월 수",
            "duration_min": "최소 소요 시간(분)",
            "duration_max": "최대 소요 시간(분)",
        }
        help_texts = {
            "age_min_months": "권장 연령: 만 5세 (60~65개월)인 경우 60을 입력하세요.",
            "age_max_months": "권장 연령: 만 5세 (60~65개월)인 경우 65를 입력하세요.",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.pk:
            self.fields["categories"].initial = self.instance.categories.all()

    def clean_categories(self):
        if not Category.objects.exists():
            raise forms.ValidationError("등록된 카테고리가 없습니다. 카테고리를 먼저 준비해 주세요.")
        return self.cleaned_data["categories"]

    def _save_m2m(self):
        super()._save_m2m()
        self.instance.categories.set(self.cleaned_data["categories"])


@admin.register(Activity)
class ActivityAdmin(admin.ModelAdmin):
    form = ActivityForm
    list_display = ("title", "difficulty", "minimum_months", "maximum_months", "price_in_won", "is_public", "updated_at")
    list_filter = ("is_public", "difficulty", "categories")
    search_fields = ("title", "description")
    readonly_fields = ("price_in_won", "created_at", "updated_at")

    @admin.display(description="최소 개월 수", ordering="age_min_months")
    def minimum_months(self, obj):
        return obj.age_min_months

    @admin.display(description="최대 개월 수", ordering="age_max_months")
    def maximum_months(self, obj):
        return obj.age_max_months

    @admin.display(description="가격(원)", ordering="price")
    def price_in_won(self, obj):
        return obj.price if obj is not None else 0
