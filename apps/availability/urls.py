from django.urls import path
from rest_framework.routers import DefaultRouter
from .views import (
    RoomRateViewSet, SeasonalRateViewSet, RestrictionViewSet, AvailabilityViewSet,
    AvailabilitySearchView, bulk_block_rooms,
)

router = DefaultRouter()
router.register(r'room-rates', RoomRateViewSet, basename='roomrate')
router.register(r'seasonal-rates', SeasonalRateViewSet, basename='seasonalrate')
router.register(r'restrictions', RestrictionViewSet, basename='restriction')
router.register(r'availability', AvailabilityViewSet, basename='availability')

urlpatterns = [
    path('availability/search/', AvailabilitySearchView.as_view(), name='availability-search'),
    path('availability/bulk-block/', bulk_block_rooms, name='availability-bulk-block'),
] + router.urls