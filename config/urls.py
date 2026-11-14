from django.contrib import admin
from django.conf import settings
from django.urls import include, path

from config.views import health

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/v1/health/", health, name="health"),
    path("api/v1/auth/", include("email_verification.urls")),
    path("api/v1/", include("accounts.urls")),
    path("api/v1/", include("children.urls")),
    path("api/v1/", include("categories.urls")),
    path("api/v1/", include("activities.urls")),
    path("api/v1/", include("favorites.urls")),
]

if settings.DEBUG:
    from config.dev_test import dev_test

    urlpatterns += [
        path("dev-test/", dev_test, name="dev-test"),
        path("dev-test/app.js", dev_test, {"asset": "app.js"}, name="dev-test-js"),
        path("dev-test/app.css", dev_test, {"asset": "app.css"}, name="dev-test-css"),
    ]
