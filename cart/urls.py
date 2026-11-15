from django.urls import path

from .views import CartCreateView, CartDeleteView, CartListView

app_name = "cart"
urlpatterns = [
    path("cart", CartListView.as_view(), name="list"),
    path("cart/items", CartCreateView.as_view(), name="create"),
    path("cart/items/<int:activity_id>", CartDeleteView.as_view(), name="delete"),
]
