from django.db import transaction
from django.utils.decorators import method_decorator
from django.views.decorators.cache import never_cache
from rest_framework import serializers
from rest_framework.exceptions import NotFound
from rest_framework.generics import GenericAPIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from activities.models import Activity
from activities.serializers import ActivitySerializer
from email_verification.errors import AuthError, auth_exception_handler
from .models import CartItem
from .serializers import CartCreateSerializer, CartQuerySerializer


@method_decorator(never_cache, name="dispatch")
class CartAPIView(GenericAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = CartCreateSerializer

    def get_exception_handler(self):
        return auth_exception_handler


class CartListView(CartAPIView):
    def get(self, request):
        query = CartQuerySerializer(data=request.query_params)
        query.is_valid(raise_exception=True)
        rows = list(CartItem.objects.filter(user=request.user, activity__is_public=True)
                    .select_related("activity").prefetch_related("activity__categories").order_by("-id"))
        activities = [row.activity for row in rows]
        return Response({"items": ActivitySerializer(activities, many=True, context={"request": request}).data,
                         "total_amount": sum(row.price for row in activities)})


class CartCreateView(CartAPIView):
    def post(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        activity_id = serializer.validated_data["activity_id"]
        with transaction.atomic():
            # Free activities need no purchase permission. Keep availability
            # checks and competing cart inserts serialized; UNIQUE also guards
            # inserts made outside this API.
            activity = Activity.objects.select_for_update().filter(pk=activity_id, is_public=True).first()
            if activity is None:
                raise serializers.ValidationError({"activity_id": "공개된 활동지를 선택해 주세요."})
            _, created = CartItem.objects.get_or_create(user=request.user, activity=activity)
            if not created:
                raise AuthError("이미 장바구니에 등록된 활동지입니다.", status=409, code="INVALID_STATE")
        return Response({"activity_id": activity_id, "message": "처리되었습니다."}, status=201)


class CartDeleteView(CartAPIView):
    def delete(self, request, activity_id):
        activity_id = serializers.IntegerField(min_value=1, max_value=9223372036854775807).run_validation(activity_id)
        deleted, _ = CartItem.objects.filter(user=request.user, activity_id=activity_id).delete()
        if not deleted:
            raise NotFound()
        return Response(status=204)
