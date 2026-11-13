import re

from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers

from email_verification.serializers import EmailField


class StrictSerializer(serializers.Serializer):
    def to_internal_value(self, data):
        if isinstance(data, dict):
            unknown = set(data) - set(self.fields)
            if unknown:
                raise serializers.ValidationError({key: ["허용되지 않은 필드입니다."] for key in unknown})
        return super().to_internal_value(data)


class SecretField(serializers.CharField):
    def __init__(self, **kwargs):
        super().__init__(write_only=True, trim_whitespace=False, **kwargs)

    def to_internal_value(self, data):
        if not isinstance(data, str):
            self.fail("invalid")
        return super().to_internal_value(data)


def check_new_password(value, user=None):
    if len(value) < 8 or not re.search(r"[A-Za-z]", value) or not re.search(r"[0-9]", value):
        raise serializers.ValidationError("영문과 숫자를 포함해 8자 이상 입력해 주세요.")
    try:
        validate_password(value, user=user)
    except DjangoValidationError as error:
        raise serializers.ValidationError(error.messages) from None
    return value


class SignupSerializer(StrictSerializer):
    identifier = EmailField()
    verification_token = SecretField()
    password = SecretField()
    agreements = serializers.JSONField()

    def validate_agreements(self, value):
        if not isinstance(value, dict):
            raise serializers.ValidationError("객체를 입력해 주세요.")
        return value

    def validate(self, attrs):
        check_new_password(attrs["password"], get_user_model()(email=attrs["identifier"]))
        return attrs


class LoginSerializer(StrictSerializer):
    email = EmailField()
    password = SecretField()


class RefreshSerializer(StrictSerializer):
    refresh_token = SecretField()


class LogoutSerializer(StrictSerializer):
    refresh_token = SecretField(required=False, allow_null=True)


class ProfileSerializer(serializers.Serializer):
    id = serializers.IntegerField(read_only=True)
    email = serializers.EmailField(read_only=True)
    phone = serializers.CharField(read_only=True)
    name = serializers.CharField(read_only=True)


class ProfileUpdateSerializer(StrictSerializer):
    name = serializers.CharField(required=False, allow_null=True, allow_blank=True)
    nickname = serializers.CharField(required=False, allow_null=True, allow_blank=True)


class PasswordChangeSerializer(StrictSerializer):
    current_password = SecretField()
    new_password = SecretField()


class PasswordResetRequestSerializer(StrictSerializer):
    email = EmailField()


class PasswordResetConfirmSerializer(StrictSerializer):
    reset_token = SecretField()
    new_password = SecretField()
