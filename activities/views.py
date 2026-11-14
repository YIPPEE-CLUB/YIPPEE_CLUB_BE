from django.db.models import Q
from django.http import FileResponse
from django.shortcuts import get_object_or_404
from rest_framework.generics import GenericAPIView
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from email_verification.errors import auth_exception_handler
from .models import Activity
from .serializers import ActivityQuerySerializer, ActivitySerializer


class ActivityAPIView(GenericAPIView):
    permission_classes = [AllowAny]
    serializer_class = ActivitySerializer

    def get_exception_handler(self):
        return auth_exception_handler

    def get_queryset(self):
        return Activity.objects.filter(is_public=True).prefetch_related("categories")


class ActivityListView(ActivityAPIView):
    def get(self, request):
        query = ActivityQuerySerializer(data=request.query_params)
        query.is_valid(raise_exception=True)
        data = query.validated_data
        rows = self.get_queryset()
        if "q" in data:
            rows = rows.filter(Q(title__icontains=data["q"]) | Q(description__icontains=data["q"]))
        if "category" in data:
            rows = rows.filter(categories__id=data["category"])
        if "age_years" in data:
            months = data["age_years"] * 12
            rows = rows.filter(age_min_months__lte=months + 11, age_max_months__gte=months)
        if "duration" in data:
            low, high = map(int, data["duration"].split("-"))
            rows = rows.filter(duration_min__lte=high, duration_max__gte=low)
        if "difficulty" in data:
            rows = rows.filter(difficulty=data["difficulty"])
        if "price_min" in data:
            rows = rows.filter(price__gte=data["price_min"])
        if "price_max" in data:
            rows = rows.filter(price__lte=data["price_max"])
        ordering = {"latest": ("-created_at", "-id"), "oldest": ("created_at", "id"),
                    "title": ("title", "id"), "price_asc": ("price", "id"), "price_desc": ("-price", "id")}
        rows = rows.order_by(*ordering[data["sort"]])
        paginator = PageNumberPagination()
        paginator.page_size = data["page_size"]
        page = paginator.paginate_queryset(rows, request, view=self)
        return paginator.get_paginated_response(self.get_serializer(page, many=True).data)


class ActivityDetailView(ActivityAPIView):
    def get(self, request, activity_id):
        row = get_object_or_404(self.get_queryset(), pk=activity_id)
        return Response(self.get_serializer(row).data)


class ActivityFileView(ActivityAPIView):
    def get(self, request, activity_id, kind):
        row = get_object_or_404(self.get_queryset(), pk=activity_id)
        if kind not in ("pdf", "image"):
            from rest_framework.exceptions import NotFound
            raise NotFound()
        file = getattr(row, kind)
        try:
            stream = file.storage.open(file.name, "rb")
        except FileNotFoundError:
            from rest_framework.exceptions import NotFound
            raise NotFound()
        response = FileResponse(stream, as_attachment=True, filename=("activity-%s" % row.pk) + (".pdf" if kind == "pdf" else "." + file.name.rsplit(".", 1)[-1]))
        response["Cache-Control"] = "private, no-store"
        response["X-Content-Type-Options"] = "nosniff"
        return response
