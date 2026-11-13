from django.contrib import admin
from django.contrib.auth import get_user_model
from django.contrib.auth.admin import UserAdmin

from .forms import EmailUserChangeForm, EmailUserCreationForm
from .models import User


class EmailUserAdmin(UserAdmin):
    form = EmailUserChangeForm
    add_form = EmailUserCreationForm
    list_display = ("email", "is_active", "is_staff", "is_superuser", "date_joined")
    search_fields = ("email",)
    ordering = ("email",)
    readonly_fields = ("last_login", "date_joined")
    fieldsets = (
        (None, {"fields": ("email", "password")}),
        ("Permissions", {"fields": ("is_active", "is_staff", "is_superuser", "groups", "user_permissions")}),
        ("Dates", {"fields": ("last_login", "date_joined")}),
    )
    add_fieldsets = ((None, {"classes": ("wide",), "fields": ("email", "password1", "password2")}),)

    # UserAdmin's built-in password change view/form is retained, so raw
    # passwords are never edited as a model field or displayed in this list.


# During bootstrap, leave Django's original UserAdmin registration untouched.
if get_user_model() is User:
    admin.site.register(User, EmailUserAdmin)
