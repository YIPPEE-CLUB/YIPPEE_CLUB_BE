from django.contrib.auth.models import AbstractBaseUser, PermissionsMixin
from django.conf import settings
from django.db import models
from django.utils import timezone

from .managers import UserManager


class User(AbstractBaseUser, PermissionsMixin):
    """Email user used by the service after the reviewed database transition."""

    # Match auth_user's existing integer PK and Admin FK type during transition.
    id = models.AutoField(primary_key=True)
    email = models.EmailField(max_length=254, unique=True)
    name = models.TextField(blank=True, default="")
    nickname = models.TextField(blank=True, default="")
    phone = models.TextField(blank=True, default="")
    agreements = models.JSONField(default=dict)
    is_staff = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    date_joined = models.DateTimeField(default=timezone.now)
    groups = models.ManyToManyField(
        "auth.Group", blank=True, related_name="yippee_users", related_query_name="yippee_user",
    )
    user_permissions = models.ManyToManyField(
        "auth.Permission", blank=True, related_name="yippee_users", related_query_name="yippee_user",
    )

    objects = UserManager()
    USERNAME_FIELD = "email"
    EMAIL_FIELD = "email"
    REQUIRED_FIELDS = []

    def save(self, *args, **kwargs):
        self.email = UserManager.normalize_email(self.email)
        super().save(*args, **kwargs)

    def __str__(self):
        return self.email


class RefreshSession(models.Model):
    """Only an HMAC of the issued refresh token is stored, never the JWT itself."""

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="refresh_sessions")
    token_digest = models.CharField(max_length=64, unique=True)
    expires_at = models.DateTimeField()
    revoked_at = models.DateTimeField(null=True)
    created_at = models.DateTimeField(default=timezone.now)
