from django.utils import timezone
from rest_framework import serializers

from accounts.serializers import StrictSerializer
from categories.models import Category

from .models import Child


class TextField(serializers.CharField):
    def to_internal_value(self, data):
        if not isinstance(data, str):
            self.fail("invalid")
        return super().to_internal_value(data)


class CategoryIdField(serializers.IntegerField):
    def __init__(self, **kwargs):
        super().__init__(min_value=1, max_value=9223372036854775807, **kwargs)

    def to_internal_value(self, data):
        if type(data) is not int:
            self.fail("invalid")
        return super().to_internal_value(data)


class ChildReadSerializer(serializers.ModelSerializer):
    interests = serializers.PrimaryKeyRelatedField(many=True, read_only=True)

    class Meta:
        model = Child
        fields = ("id", "name", "birth_date", "gender", "interests")
        read_only_fields = fields


class ChildCreateSerializer(StrictSerializer):
    name = TextField()
    birth_date = serializers.DateField()
    gender = TextField(required=False, allow_null=True, allow_blank=True)
    interests = serializers.ListField(child=CategoryIdField(), required=False, allow_null=True)

    def validate_birth_date(self, value):
        if value is not None and value > timezone.localdate():
            raise serializers.ValidationError("미래의 생년월일은 사용할 수 없습니다.")
        return value

    def validate_gender(self, value):
        return "" if value is None else value

    def validate_interests(self, value):
        if value is None:
            return []
        if len(value) != len(set(value)):
            raise serializers.ValidationError("중복 관심 카테고리는 사용할 수 없습니다.")
        # Writers call is_valid inside atomic. Lock valid catalogue rows until
        # their child-interest links commit, preventing concurrent deletion.
        categories = list(Category.objects.select_for_update().filter(pk__in=value).order_by("pk"))
        if len(categories) != len(value):
            raise serializers.ValidationError("존재하지 않는 카테고리입니다.")
        return categories

    def create(self, validated_data):
        interests = validated_data.pop("interests", [])
        child = Child.objects.create(user=self.context["request"].user, **validated_data)
        child.interests.set(interests)
        return child


class ChildUpdateSerializer(ChildCreateSerializer):
    name = TextField(required=False, allow_null=False)
    birth_date = serializers.DateField(required=False, allow_null=False)

    def update(self, instance, validated_data):
        interests = validated_data.pop("interests", None)
        for key, value in validated_data.items():
            setattr(instance, key, value)
        if validated_data:
            instance.save(update_fields=list(validated_data))
        if interests is not None:
            instance.interests.set(interests)
        return instance
