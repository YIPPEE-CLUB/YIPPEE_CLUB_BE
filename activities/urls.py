from django.urls import path
from .views import ActivityListView, ActivityDetailView, ActivityFileView

app_name = "activities"
urlpatterns = [
    path("activities", ActivityListView.as_view(), name="list"),
    path("activities/<int:activity_id>", ActivityDetailView.as_view(), name="detail"),
    path("activities/<int:activity_id>/files/<str:kind>", ActivityFileView.as_view(), name="file"),
]
