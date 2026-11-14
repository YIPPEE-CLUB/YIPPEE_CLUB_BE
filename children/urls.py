from django.urls import path

from .views import ChildDetailView, ChildListCreateView

app_name = "children"
urlpatterns = [
    path("children", ChildListCreateView.as_view(), name="list"),
    path("children/<int:child_id>", ChildDetailView.as_view(), name="detail"),
]
