"""Environment-based settings for YIPPEE CLUB."""
from datetime import timedelta
from pathlib import Path

import environ
from django.core.exceptions import ImproperlyConfigured

BASE_DIR = Path(__file__).resolve().parent.parent

env = environ.Env(DEBUG=(bool, False))
environ.Env.read_env(BASE_DIR / ".env")

SECRET_KEY = env("SECRET_KEY")
DEBUG = env.bool("DEBUG")
ALLOWED_HOSTS = env.list("ALLOWED_HOSTS", default=[])

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "rest_framework",
    "corsheaders",
    "accounts.apps.AccountsConfig",
    "email_verification.apps.EmailVerificationConfig",
    "categories.apps.CategoriesConfig",
    "children.apps.ChildrenConfig",
    "activities.apps.ActivitiesConfig",
    "favorites.apps.FavoritesConfig",
]

# Existing databases must complete the legacy bootstrap before deploying this
# setting. See docs/USER_MIGRATION_STAGE1.md; changing settings alone is unsafe.
AUTH_USER_MODEL = "accounts.User"

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"
TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]
WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.mysql",
        "NAME": env("MYSQL_DATABASE"),
        "USER": env("MYSQL_USER"),
        "PASSWORD": env("MYSQL_PASSWORD"),
        "HOST": env("MYSQL_HOST"),
        "PORT": env.int("MYSQL_PORT"),
        "OPTIONS": {
            "charset": "utf8mb4",
            "init_command": "SET sql_mode='STRICT_TRANS_TABLES'",
        },
    }
}

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework_simplejwt.authentication.JWTAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticated",
    ],
    "DEFAULT_RENDERER_CLASSES": ["rest_framework.renderers.JSONRenderer"],
}
# Configurable defaults until the v1.5 token lifetime policy is finalized.
# Password changes invalidate previously issued access/refresh credentials.
SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(seconds=env.int("JWT_ACCESS_TTL_SECONDS", default=300)),
    "REFRESH_TOKEN_LIFETIME": timedelta(seconds=env.int("JWT_REFRESH_TTL_SECONDS", default=86400)),
    "CHECK_REVOKE_TOKEN": True,
}
PASSWORD_RESET_TIMEOUT = env.int("PASSWORD_RESET_TIMEOUT", default=600)
CORS_ALLOWED_ORIGINS = env.list("CORS_ALLOWED_ORIGINS", default=[])

LANGUAGE_CODE = "ko-kr"
TIME_ZONE = "Asia/Seoul"
USE_I18N = True
USE_TZ = True
STATIC_URL = "static/"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# Never expose this directory using MEDIA_URL, a web server alias or a public bucket.
ACTIVITY_PRIVATE_ROOT = BASE_DIR / "private_uploads"
ACTIVITY_PDF_MAX_BYTES = 20 * 1024 * 1024
ACTIVITY_IMAGE_MAX_BYTES = 5 * 1024 * 1024
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
    "activities": {"BACKEND": "activities.storage.PrivateActivityStorage"},
}

# Development policy defaults; values are configurable and not final v1.5 policy.
AUTH_CODE_TTL_SECONDS = env.int("AUTH_CODE_TTL_SECONDS", default=180)
AUTH_VERIFICATION_TOKEN_TTL_SECONDS = env.int("AUTH_VERIFICATION_TOKEN_TTL_SECONDS", default=600)
AUTH_CODE_MAX_ATTEMPTS = env.int("AUTH_CODE_MAX_ATTEMPTS", default=5)
AUTH_SEND_COOLDOWN_SECONDS = env.int("AUTH_SEND_COOLDOWN_SECONDS", default=60)
AUTH_RATE_WINDOW_SECONDS = env.int("AUTH_RATE_WINDOW_SECONDS", default=600)
AUTH_IP_LIMIT = env.int("AUTH_IP_LIMIT", default=30)
AUTH_EMAIL_LIMIT = env.int("AUTH_EMAIL_LIMIT", default=10)
EMAIL_BACKEND = env("EMAIL_BACKEND", default="django.core.mail.backends.smtp.EmailBackend")
EMAIL_HOST = env("EMAIL_HOST", default="localhost")
EMAIL_PORT = env.int("EMAIL_PORT", default=587)
EMAIL_HOST_USER = env("EMAIL_HOST_USER", default="")
EMAIL_HOST_PASSWORD = env("EMAIL_HOST_PASSWORD", default="")
EMAIL_USE_TLS = env.bool("EMAIL_USE_TLS", default=True)
EMAIL_USE_SSL = env.bool("EMAIL_USE_SSL", default=False)
EMAIL_TIMEOUT = env.int("EMAIL_TIMEOUT", default=10)
DEFAULT_FROM_EMAIL = env("DEFAULT_FROM_EMAIL", default="noreply@example.com")

# Tests must use a separate MySQL schema; never reuse the development database.
DATABASES["default"]["TEST"] = {
    "NAME": env("MYSQL_TEST_DATABASE", default="test_yippee_club_db"),
}
_test_database = DATABASES["default"]["TEST"]["NAME"]
if (not _test_database.startswith("test_yippee_") or
        _test_database.casefold() == DATABASES["default"]["NAME"].casefold()):
    raise ImproperlyConfigured(
        "MYSQL_TEST_DATABASE must start with test_yippee_ and differ from the development database."
    )
