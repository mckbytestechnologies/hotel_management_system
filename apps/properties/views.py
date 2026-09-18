from rest_framework import viewsets, filters
from django_filters.rest_framework import DjangoFilterBackend

from .models import Property, RoomType, Room, RatePlan
from .serializers import (
    PropertySerializer, RoomTypeSerializer, RoomSerializer, RatePlanSerializer
)


class PropertyViewSet(viewsets.ModelViewSet):
    """
    CRUD API for Properties.
    /api/properties/          -> list, create
    /api/properties/{id}/     -> retrieve, update, delete
    """
    queryset = Property.objects.all()
    serializer_class = PropertySerializer
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['is_active', 'city', 'country']
    search_fields = ['name', 'code', 'city']
    ordering_fields = ['name', 'created_at']


class RoomTypeViewSet(viewsets.ModelViewSet):
    """
    CRUD API for Room Types.
    Supports filtering by property: /api/room-types/?property=1
    """
    queryset = RoomType.objects.select_related('property').all()
    serializer_class = RoomTypeSerializer
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['property', 'is_active']
    search_fields = ['name', 'code']
    ordering_fields = ['name', 'created_at']


class RoomViewSet(viewsets.ModelViewSet):
    """
    CRUD API for individual Rooms.
    Supports filtering by property, room_type, and status:
    /api/rooms/?property=1&status=AVAILABLE
    """
    queryset = Room.objects.select_related('property', 'room_type').all()
    serializer_class = RoomSerializer
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['property', 'room_type', 'status', 'is_active']
    search_fields = ['room_number']
    ordering_fields = ['room_number', 'created_at']


class RatePlanViewSet(viewsets.ModelViewSet):
    """
    CRUD API for Rate Plans.
    """
    queryset = RatePlan.objects.select_related('property').all()
    serializer_class = RatePlanSerializer
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['property', 'is_refundable', 'is_active']
    search_fields = ['name', 'code']
    ordering_fields = ['name', 'created_at']