from datetime import timedelta

from django.utils import timezone
from rest_framework import filters, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from analytics.services import build_analytics
from inventory.models import EXPIRING_SOON_DAYS, FoodItem, FoodLog

from .serializers import FoodItemSerializer, FoodLogSerializer


class FoodItemViewSet(viewsets.ModelViewSet):
    """List, create, read, update and delete the logged-in user's food items."""

    serializer_class = FoodItemSerializer
    filter_backends = [filters.SearchFilter, filters.OrderingFilter]
    search_fields = ["name"]
    ordering_fields = ["expiry_date", "name", "quantity", "purchase_date"]
    ordering = ["expiry_date", "name"]

    def get_queryset(self):
        # Every query starts from the logged-in user's own items only.
        queryset = FoodItem.objects.filter(owner=self.request.user)
        params = self.request.query_params

        category = params.get("category")
        if category:
            if category not in FoodItem.Category.values:
                allowed = ", ".join(FoodItem.Category.values)
                raise ValidationError(
                    {"category": f"Unknown category. Choose from: {allowed}."}
                )
            queryset = queryset.filter(category=category)

        status = params.get("status")
        if status:
            today = timezone.localdate()
            soon_cutoff = today + timedelta(days=EXPIRING_SOON_DAYS)
            if status == "expired":
                queryset = queryset.filter(expiry_date__lt=today)
            elif status == "expiring_soon":
                queryset = queryset.filter(
                    expiry_date__gte=today, expiry_date__lte=soon_cutoff
                )
            elif status == "fresh":
                queryset = queryset.filter(expiry_date__gt=soon_cutoff)
            else:
                raise ValidationError(
                    {"status": "Unknown status. Choose from: expired, expiring_soon, fresh."}
                )

        return queryset

    def perform_create(self, serializer):
        # The owner always comes from the login, never from the request body.
        serializer.save(owner=self.request.user)

    @action(detail=False, methods=["get"])
    def expiring(self, request):
        """Items that are not expired yet but expire within the next few days."""
        today = timezone.localdate()
        cutoff = today + timedelta(days=EXPIRING_SOON_DAYS)
        items = FoodItem.objects.filter(
            owner=request.user, expiry_date__gte=today, expiry_date__lte=cutoff
        ).order_by("expiry_date", "name")
        serializer = self.get_serializer(items, many=True)
        return Response(serializer.data)


class FoodLogViewSet(viewsets.ReadOnlyModelViewSet):
    """Read the logged-in user's consumption and waste records."""

    serializer_class = FoodLogSerializer

    def get_queryset(self):
        queryset = FoodLog.objects.filter(owner=self.request.user)
        action_filter = self.request.query_params.get("action")
        if action_filter:
            if action_filter not in FoodLog.Action.values:
                raise ValidationError(
                    {"action": "Unknown action. Choose from: consumed, wasted."}
                )
            queryset = queryset.filter(action=action_filter)
        return queryset


class AnalyticsSummaryView(APIView):
    """The same Pandas statistics and chart data as the Analytics page."""

    def get(self, request):
        data = build_analytics(request.user)
        if data is None:
            return Response({"has_data": False, "stats": None, "charts": None})
        return Response({"has_data": True, **data})