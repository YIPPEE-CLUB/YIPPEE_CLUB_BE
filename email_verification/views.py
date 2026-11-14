from django.contrib.auth import get_user_model
from django.conf import settings
from django.utils.decorators import method_decorator
from django.views.decorators.debug import sensitive_post_parameters
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from . import serializers, verification
from .errors import AuthError, auth_exception_handler
from .security import consume_limit, limit_request


@method_decorator(sensitive_post_parameters(), name="dispatch")
class AuthView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]
    serializer_class = None
    scope = "auth"

    def get_exception_handler(self):
        return auth_exception_handler

    def post(self, request):
        limit_request(request, self.scope)
        serializer = self.serializer_class(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        identifier = data.get("identifier", data.get("email"))
        if identifier:
            # The IP limit was already consumed before parsing user input.
            consume_limit(f"{self.scope}:email", identifier, settings.AUTH_EMAIL_LIMIT,
                          settings.AUTH_RATE_WINDOW_SECONDS)
        return self.perform(data)


class IdentifierCheckView(AuthView):
    serializer_class = serializers.IdentifierSerializer
    scope = "identifier-check"

    def perform(self, data):
        registered = get_user_model().objects.filter(email__iexact=data["identifier"]).exists()
        return Response({"registered": registered, "identifier_type": "email"})


class VerificationSendView(AuthView):
    serializer_class = serializers.SendSerializer
    scope = "verification-send"

    def perform(self, data):
        if get_user_model().objects.filter(email__iexact=data["identifier"]).exists():
            raise AuthError("이미 가입한 이메일입니다.", status=409, code="ALREADY_EXISTS")
        challenge = verification.send_verification(data["identifier"])
        return Response({"verification_id": challenge.pk,
                         "expires_in_seconds": settings.AUTH_CODE_TTL_SECONDS})


class VerificationConfirmView(AuthView):
    serializer_class = serializers.ConfirmSerializer
    scope = "verification-confirm"

    def perform(self, data):
        token = verification.confirm_verification(data["verification_id"], data["code"])
        return Response({"verification_token": token, "verified": True})
