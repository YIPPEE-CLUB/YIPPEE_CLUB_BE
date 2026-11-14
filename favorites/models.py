from django.conf import settings
from django.db import models


class Favorite(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="favorites")
    activity = models.ForeignKey("activities.Activity", on_delete=models.CASCADE, related_name="favorites")

    class Meta:
        db_table = "favorites"
        ordering = ("-id",)
        constraints = [models.UniqueConstraint(fields=("user", "activity"), name="unique_user_activity_favorite")]
