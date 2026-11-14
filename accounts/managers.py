from django.contrib.auth.base_user import BaseUserManager
from django.core.validators import validate_email


class UserManager(BaseUserManager):
    use_in_migrations = True

    @classmethod
    def normalize_email(cls, email):
        return super().normalize_email(email.strip()).lower() if email else ""

    def create_user(self, email, password=None, **extra_fields):
        email = self.normalize_email(email)
        if not email:
            raise ValueError("An email address is required.")
        validate_email(email)
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        extra_fields.setdefault("is_active", True)
        if any(extra_fields.get(name) is not True for name in ("is_staff", "is_superuser", "is_active")):
            raise ValueError("A superuser must be active, staff and superuser.")
        if not password:
            raise ValueError("A superuser password is required.")
        return self.create_user(email, password, **extra_fields)
