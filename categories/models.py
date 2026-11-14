from django.db import models


class Category(models.Model):
    """One catalogue for both child interests and future activity categories."""

    name = models.TextField()

    class Meta:
        db_table = "categories"
        ordering = ("id",)

    def __str__(self):
        return self.name
