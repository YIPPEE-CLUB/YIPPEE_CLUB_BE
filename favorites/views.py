from django.db import transaction
from rest_framework import serializers
from rest_framework.generics import GenericAPIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.exceptions import NotFound

from activities.models import Activity
from activities.serializers import ActivitySerializer
from email_verification.errors import AuthError, auth_exception_handler
from .models import Favorite
from .serializers import FavoriteCreateSerializer, FavoritePageSerializer


class FavoriteAPIView(GenericAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = FavoriteCreateSerializer

    def get_exception_handler(self):
        return auth_exception_handler


class FavoriteListCreateView(FavoriteAPIView):
    def get(self, request):
        query = FavoritePageSerializer(data=request.query_params)
        query.is_valid(raise_exception=True)
        page, size = query.validated_data["page"], query.validated_data["page_size"]
        offset = (page - 1) * size
        rows = (Favorite.objects.filter(user=request.user, activity__is_public=True)
                .select_related("activity").prefetch_related("activity__categories")
                .order_by("-id")[offset:offset + size])
        return Response({"results": ActivitySerializer(
            [row.activity for row in rows], many=True, context={"request": request}).data})

    def post(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        activity_id = serializer.validated_data["activity_id"]
        with transaction.atomic():
            # Keep deletion/unpublishing from racing the availability check and
            # serialize competing API inserts for this activity. UNIQUE is the
            # final guard, including writes made outside this API.
            activity = Activity.objects.select_for_update().filter(pk=activity_id, is_public=True).first()
            if activity is None:
                # The POST contract has 400, not 404; unavailable IDs share one error.
                raise serializers.ValidationError({"activity_id": "공개된 활동지를 선택해 주세요."})
            _, created = Favorite.objects.get_or_create(user=request.user, activity=activity)
            if not created:
                raise AuthError("이미 즐겨찾기에 등록된 활동지입니다.", status=409, code="INVALID_STATE")
        return Response({"activity_id": activity_id, "message": "처리되었습니다."}, status=201)


class FavoriteDeleteView(FavoriteAPIView):
    def delete(self, request, activity_id):
        field = serializers.IntegerField(min_value=1, max_value=9223372036854775807)
        try:
            activity_id = field.run_validation(activity_id)
        except serializers.ValidationError:
            raise serializers.ValidationError({"activity_id": "활동지 ID를 확인해 주세요."}) from None
        # Delete by owner+activity even when hidden, so a saved hidden item can
        # still be removed. Never look up another user's relationship.
        deleted, _ = Favorite.objects.filter(user=request.user, activity_id=activity_id).delete()
        if not deleted:
            raise NotFound()
        return Response(status=204)
