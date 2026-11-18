from django.contrib.auth import get_user_model
from django.db import transaction
from django.utils.decorators import method_decorator
from django.views.decorators.cache import never_cache
from rest_framework import serializers
from rest_framework.generics import GenericAPIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from email_verification.errors import auth_exception_handler

from .models import Child
from .permissions import IsChildOwner
from .serializers import ActiveChildSerializer, ChildCreateSerializer, ChildReadSerializer, ChildUpdateSerializer


@method_decorator(never_cache, name="dispatch")
class ChildAPIView(GenericAPIView):
    permission_classes = [IsAuthenticated, IsChildOwner]
    lookup_url_kwarg = "child_id"
    serializer_class = ChildReadSerializer

    def get_exception_handler(self):
        return auth_exception_handler

    def get_queryset(self):
        return Child.objects.filter(user=self.request.user).prefetch_related("interests")

    def get_locked_object(self):
        # Ownership filtering runs in SQL, before validation or mutation.
        from django.shortcuts import get_object_or_404

        child = get_object_or_404(self.get_queryset().select_for_update(), pk=self.kwargs["child_id"])
        self.check_object_permissions(self.request, child)
        return child


class ChildListCreateView(ChildAPIView):
    def get(self, request):
        return Response({"results": ChildReadSerializer(self.get_queryset(), many=True).data})

    def post(self, request):
        with transaction.atomic():
            serializer = ChildCreateSerializer(data=request.data, context={"request": request})
            serializer.is_valid(raise_exception=True)
            child = serializer.save()
            return Response(ChildReadSerializer(child).data, status=201)


class ChildDetailView(ChildAPIView):
    def get(self, request, child_id):
        return Response(ChildReadSerializer(self.get_object()).data)

    def patch(self, request, child_id):
        with transaction.atomic():
            child = self.get_locked_object()
            serializer = ChildUpdateSerializer(child, data=request.data, context={"request": request})
            serializer.is_valid(raise_exception=True)
            return Response(ChildReadSerializer(serializer.save()).data)

    def delete(self, request, child_id):
        with transaction.atomic():
            child = self.get_locked_object()
            # Match selection's Child -> User lock order. Serializing the owner
            # prevents deletion from clearing a concurrently changed selection.
            get_user_model().objects.select_for_update().get(pk=request.user.pk)
            child.delete()
        return Response(status=204)


class ActiveChildView(ChildAPIView):
    serializer_class = ActiveChildSerializer

    def put(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        with transaction.atomic():
            # Same lock order as child deletion, including selecting a sibling.
            child = Child.objects.select_for_update().filter(
                pk=serializer.validated_data["child_id"], user=request.user,
            ).first()
            if child is None:
                # API 25 defines 400, not 404. Do not disclose other owners.
                raise serializers.ValidationError({"child_id": "본인의 아이를 선택해 주세요."})
            self.check_object_permissions(request, child)
            user = get_user_model().objects.select_for_update().get(pk=request.user.pk)
            if user.active_child_id != child.pk:
                user.active_child_id = child.pk
                user.save(update_fields=["active_child"])
        return Response({"active_child_id": child.pk})
