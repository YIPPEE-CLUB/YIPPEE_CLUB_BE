from django.urls import path

from .views import FavoriteDeleteView, FavoriteListCreateView

app_name = "favorites"
urlpatterns = [
    path("favorites", FavoriteListCreateView.as_view(), name="list"),
    path("favorites/<int:activity_id>", FavoriteDeleteView.as_view(), name="delete"),
]
