from django.conf import settings
from django.db import models
from django.utils import timezone


class PurchaseEntitlement(models.Model):
    class Status(models.TextChoices):
        ACTIVE = "active", "유효"
        REVOKED = "revoked", "회수"

    # Preserve the permission record until a deliberate retention policy exists.
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="purchase_entitlements")
    activity = models.ForeignKey("activities.Activity", on_delete=models.PROTECT, related_name="purchase_entitlements")
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.ACTIVE)
    granted_at = models.DateTimeField(default=timezone.now)
    revoked_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "purchase_entitlements"
        constraints = [
            models.UniqueConstraint(fields=("user", "activity"), name="unique_user_activity_entitlement"),
            models.CheckConstraint(
                condition=(models.Q(status="active", revoked_at__isnull=True)
                           | models.Q(status="revoked", revoked_at__isnull=False)),
                name="entitlement_status_revoked_at"),
        ]
