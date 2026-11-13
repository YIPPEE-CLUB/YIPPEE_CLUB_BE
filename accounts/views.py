from django.contrib.auth import get_user_model
from django.db import transaction
from django.utils.decorators import method_decorator
from django.views.decorators.debug import sensitive_post_parameters
from rest_framework.response import Response
from rest_framework.views import APIView

from email_verification.errors import auth_exception_handler
from email_verification.security import limit_request
from email_verification.views import AuthView

from . import serializers, services

MESSAGE = {"message": "처리되었습니다."}


class SignupView(AuthView):
    serializer_class = serializers.SignupSerializer
    scope = "signup"

    def perform(self, data):
        return Response(services.signup(data), status=201)


class LoginView(AuthView):
    serializer_class = serializers.LoginSerializer
    scope = "login"

    def perform(self, data):
        user, tokens = services.login(data["email"], data["password"])
        return Response({**tokens, "user": serializers.ProfileSerializer(user).data})


class RefreshView(AuthView):
    serializer_class = serializers.RefreshSerializer
    scope = "refresh"

    def perform(self, data):
        return Response(services.refresh(data["refresh_token"]))


class LogoutView(AuthView):
    serializer_class = serializers.LogoutSerializer
    scope = "logout"

    def perform(self, data):
        services.logout(data.get("refresh_token"))
        return Response(MESSAGE)


class PasswordResetRequestView(AuthView):
    serializer_class = serializers.PasswordResetRequestSerializer
    scope = "password-reset-request"

    def perform(self, data):
        services.request_password_reset(data["email"])
        return Response(MESSAGE)


class PasswordResetConfirmView(AuthView):
    serializer_class = serializers.PasswordResetConfirmSerializer
    scope = "password-reset-confirm"

    def perform(self, data):
        services.confirm_password_reset(data["reset_token"], data["new_password"])
        return Response(MESSAGE)


@method_decorator(sensitive_post_parameters(), name="dispatch")
class UserView(APIView):
    # Global JWTAuthentication + IsAuthenticated apply to every method.
    def get_exception_handler(self):
        return auth_exception_handler


class ProfileView(UserView):
    def get(self, request):
        return Response(serializers.ProfileSerializer(request.user).data)

    def patch(self, request):
        serializer = serializers.ProfileUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        with transaction.atomic():
            user = get_user_model().objects.select_for_update().get(pk=request.user.pk)
            for key, value in serializer.validated_data.items():
                setattr(user, key, "" if value is None else value)
            if serializer.validated_data:
                user.save(update_fields=list(serializer.validated_data))
            return Response(serializers.ProfileSerializer(user).data)


class PasswordChangeView(UserView):
    def patch(self, request):
        limit_request(request, "password-change", str(request.user.pk))
        serializer = serializers.PasswordChangeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        services.change_password(request.user.pk, **serializer.validated_data)
        return Response(MESSAGE)
