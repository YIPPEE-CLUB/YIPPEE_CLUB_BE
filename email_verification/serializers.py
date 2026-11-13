from rest_framework import serializers


class EmailField(serializers.EmailField):
    def __init__(self, **kwargs):
        super().__init__(max_length=254, **kwargs)

    def to_internal_value(self, data):
        return super().to_internal_value(data).lower()


class IdentifierSerializer(serializers.Serializer):
    identifier = EmailField()


class SendSerializer(IdentifierSerializer):
    purpose = serializers.ChoiceField(choices=["signup"])


class VerificationCodeField(serializers.RegexField):
    def to_internal_value(self, data):
        if not isinstance(data, str):
            self.fail("invalid")
        return super().to_internal_value(data)


class ConfirmSerializer(serializers.Serializer):
    verification_id = serializers.CharField(max_length=80)
    code = VerificationCodeField(r"^[0-9]{6}$", trim_whitespace=False, write_only=True)
