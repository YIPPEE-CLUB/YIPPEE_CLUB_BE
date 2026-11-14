from django.conf import settings
from django.db import models


class Child(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="children")
    name = models.TextField()
    birth_date = models.DateField()
    gender = models.TextField(blank=True, default="")
    interests = models.ManyToManyField("categories.Category", through="ChildInterest", related_name="interested_children")

    class Meta:
        db_table = "children"
        ordering = ("id",)


class ChildInterest(models.Model):
    child = models.ForeignKey(Child, on_delete=models.CASCADE)
    category = models.ForeignKey("categories.Category", on_delete=models.PROTECT)

    class Meta:
        db_table = "child_interests"
        constraints = [models.UniqueConstraint(fields=("child", "category"), name="unique_child_category_interest")]


class ActivityRecord(models.Model):
    """Deletion-policy anchor; activity-record authoring/catalogue fields are future work.

    Child deletion cascades to these records, never to their User or Category.
    Orders and payments must not depend on this cascade relationship.
    """

    child = models.ForeignKey(Child, on_delete=models.CASCADE, related_name="activity_records")

    class Meta:
        db_table = "activity_records"
