from django.urls import path

from . import views

app_name = "accounts"
urlpatterns = [
    path("auth/signup", views.SignupView.as_view(), name="signup"),
    path("auth/login", views.LoginView.as_view(), name="login"),
    path("auth/token/refresh", views.RefreshView.as_view(), name="refresh"),
    path("auth/logout", views.LogoutView.as_view(), name="logout"),
    path("auth/password/reset-request", views.PasswordResetRequestView.as_view(), name="password-reset-request"),
    path("auth/password/reset-confirm", views.PasswordResetConfirmView.as_view(), name="password-reset-confirm"),
    path("users/me", views.ProfileView.as_view(), name="profile"),
    path("users/me/password", views.PasswordChangeView.as_view(), name="password-change"),
]
