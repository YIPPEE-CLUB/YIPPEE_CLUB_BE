from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from accounts.views import UserView

from .models import Category
from .serializers import CategorySerializer


class CategoryListView(UserView):
    # Shared catalogue contains no user data. Supplied JWTs still use the
    # existing global authenticator; invalid credentials remain a 401.
    permission_classes = [AllowAny]

    def get(self, request):
        return Response({"results": CategorySerializer(Category.objects.all(), many=True).data})
