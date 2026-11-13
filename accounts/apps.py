from django.apps import AppConfig


def block_preview_sql(execute, sql, params, many, context):
    from django.core.exceptions import ImproperlyConfigured

    raise ImproperlyConfigured("Offline User preview forbids database SQL; use only DB-free checks.")


class AccountsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "accounts"

    def ready(self):
        from django.conf import settings
        from django.db import connections

        if getattr(settings, "USER_MODEL_OFFLINE_PREVIEW", False):
            connections["default"].execute_wrappers.append(block_preview_sql)
        if getattr(settings, "IS_USER_MODEL_REHEARSAL", False):
            from config.user_model_rehearsal import guard_rehearsal_sql

            connections["default"].execute_wrappers.append(guard_rehearsal_sql)
