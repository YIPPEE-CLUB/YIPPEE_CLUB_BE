from django.conf import settings
from django.db import models


class CartItem(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="cart_items")
    activity = models.ForeignKey("activities.Activity", on_delete=models.CASCADE, related_name="cart_items")

    class Meta:
        db_table = "cart_items"
        ordering = ("-id",)
        constraints = [models.UniqueConstraint(fields=("user", "activity"), name="unique_user_activity_cart")]
