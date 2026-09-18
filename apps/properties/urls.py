from rest_framework.routers import DefaultRouter
from .views import PropertyViewSet, RoomTypeViewSet, RoomViewSet, RatePlanViewSet

router = DefaultRouter()
router.register(r'properties', PropertyViewSet, basename='property')
router.register(r'room-types', RoomTypeViewSet, basename='roomtype')
router.register(r'rooms', RoomViewSet, basename='room')
router.register(r'rate-plans', RatePlanViewSet, basename='rateplan')

urlpatterns = router.urls