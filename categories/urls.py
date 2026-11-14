from django.urls import path

from .views import CategoryListView

app_name = "categories"
urlpatterns = [path("activity-categories", CategoryListView.as_view(), name="list")]
