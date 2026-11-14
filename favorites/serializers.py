from rest_framework import serializers

from accounts.serializers import StrictSerializer


class FavoriteCreateSerializer(StrictSerializer):
    activity_id = serializers.IntegerField(min_value=1, max_value=9223372036854775807)

    def to_internal_value(self, data):
        if isinstance(data, dict) and "activity_id" in data and type(data["activity_id"]) is not int:
            raise serializers.ValidationError({"activity_id": "정수 ID를 입력해 주세요."})
        return super().to_internal_value(data)


class FavoritePageSerializer(StrictSerializer):
    page = serializers.IntegerField(min_value=1, max_value=2147483647, default=1)
    page_size = serializers.IntegerField(min_value=1, max_value=100, default=20)
