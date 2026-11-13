from django.urls import path

from . import views

app_name = "email_verification"
urlpatterns = [
    path("identifiers/check", views.IdentifierCheckView.as_view(), name="identifier-check"),
    path("verification/send", views.VerificationSendView.as_view(), name="verification-send"),
    path("verification/confirm", views.VerificationConfirmView.as_view(), name="verification-confirm"),
]
