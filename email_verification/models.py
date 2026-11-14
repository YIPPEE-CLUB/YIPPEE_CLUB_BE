import secrets
from django.db import models
from django.utils import timezone


def verification_id():
    return "ver_" + secrets.token_hex(24)


class EmailVerification(models.Model):
    id = models.CharField(primary_key=True, max_length=80, default=verification_id, editable=False)
    email = models.EmailField(max_length=254, db_index=True)
    purpose = models.CharField(max_length=32, default="signup")
    code_digest = models.CharField(max_length=64)
    attempts = models.PositiveIntegerField(default=0)
    expires_at = models.DateTimeField()
    verified_at = models.DateTimeField(null=True)
    token_digest = models.CharField(max_length=64, unique=True, null=True)
    token_expires_at = models.DateTimeField(null=True)
    consumed_at = models.DateTimeField(null=True)
    created_at = models.DateTimeField(default=timezone.now)


class AuthRateLimit(models.Model):
    key = models.CharField(primary_key=True, max_length=64)
    window_start = models.DateTimeField()
    count = models.PositiveIntegerField(default=0)
