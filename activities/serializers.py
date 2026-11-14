from rest_framework import serializers
from django.urls import reverse

from .models import Activity


class ActivitySerializer(serializers.ModelSerializer):
    sale_status = serializers.SerializerMethodField()
    image = serializers.SerializerMethodField()
    pdf = serializers.SerializerMethodField()
    categories = serializers.PrimaryKeyRelatedField(many=True, read_only=True)

    class Meta:
        model = Activity
        fields = ("id", "title", "price", "sale_status", "description", "age_min_months",
                  "age_max_months", "difficulty", "duration_min", "duration_max", "categories", "image", "pdf")
        read_only_fields = fields

    def get_sale_status(self, obj):
        return "on_sale"

    def file_url(self, obj, kind):
        return self.context["request"].build_absolute_uri(reverse("activities:file", args=[obj.pk, kind]))

    def get_image(self, obj):
        return self.file_url(obj, "image")

    def get_pdf(self, obj):
        return self.file_url(obj, "pdf")


class ActivityQuerySerializer(serializers.Serializer):
    q = serializers.CharField(required=False, max_length=255)
    category = serializers.IntegerField(required=False, min_value=1, max_value=9223372036854775807)
    age_years = serializers.IntegerField(required=False, min_value=0, max_value=5460)
    duration = serializers.RegexField(r"^[0-9]{1,5}-[0-9]{1,5}$", required=False)
    difficulty = serializers.ChoiceField(choices=Activity.Difficulty.choices, required=False)
    price_min = serializers.IntegerField(required=False, min_value=0)
    price_max = serializers.IntegerField(required=False, min_value=0)
    sort = serializers.ChoiceField(choices=["latest", "oldest", "title", "price_asc", "price_desc"], required=False, default="latest")
    page = serializers.IntegerField(min_value=1, required=False, default=1)
    page_size = serializers.IntegerField(min_value=1, max_value=100, required=False, default=20)

    def validate(self, attrs):
        if "duration" in attrs:
            low, high = map(int, attrs["duration"].split("-"))
            if low < 1 or high < low or high > 65535:
                raise serializers.ValidationError({"duration": "소요 시간 범위를 확인해 주세요."})
        if attrs.get("price_min", 0) > attrs.get("price_max", float("inf")):
            raise serializers.ValidationError({"price_max": "가격 범위를 확인해 주세요."})
        return attrs
