from django.contrib.auth.forms import BaseUserCreationForm, UserChangeForm

from .managers import UserManager
from .models import User


class EmailNormalizationMixin:
    def clean_email(self):
        return UserManager.normalize_email(self.cleaned_data["email"])


class EmailUserCreationForm(EmailNormalizationMixin, BaseUserCreationForm):
    class Meta(BaseUserCreationForm.Meta):
        model = User
        fields = ("email",)
        field_classes = {}


class EmailUserChangeForm(EmailNormalizationMixin, UserChangeForm):
    class Meta(UserChangeForm.Meta):
        model = User
        fields = "__all__"
        field_classes = {}
