from django.urls import path

from .views import ActiveChildView, ChildDetailView, ChildListCreateView

app_name = "children"
urlpatterns = [
    path("users/me/active-child", ActiveChildView.as_view(), name="active-child"),
    path("children", ChildListCreateView.as_view(), name="list"),
    path("children/<int:child_id>", ChildDetailView.as_view(), name="detail"),
]
