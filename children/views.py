from django.db import transaction
from rest_framework.generics import GenericAPIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from email_verification.errors import auth_exception_handler

from .models import Child
from .permissions import IsChildOwner
from .serializers import ChildCreateSerializer, ChildReadSerializer, ChildUpdateSerializer


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
            self.get_locked_object().delete()
        return Response(status=204)
