from accounts.serializers import StrictSerializer
from favorites.serializers import FavoriteCreateSerializer


class CartCreateSerializer(FavoriteCreateSerializer):
    """The activity identifier has the same strict JSON contract as favorites."""


class CartQuerySerializer(StrictSerializer):
    """v1.5 defines neither pagination nor query filters for the cart."""
