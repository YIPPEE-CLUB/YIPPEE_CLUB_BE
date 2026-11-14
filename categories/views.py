from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from accounts.views import UserView

from .models import Category
from .serializers import CategorySerializer


class CategoryListView(UserView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response({"results": CategorySerializer(Category.objects.all(), many=True).data})
