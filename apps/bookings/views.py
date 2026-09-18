from rest_framework import viewsets, status
from rest_framework.response import Response
from rest_framework.decorators import action
from django.shortcuts import get_object_or_404
from django.core.exceptions import ValidationError

from apps.properties.models import Property
from apps.guests.models import Guest
from .models import Booking
from .serializers import BookingSerializer, BookingCreateSerializer
from .services import create_booking, RoomNotAvailableError


class BookingViewSet(viewsets.ModelViewSet):
    queryset = Booking.objects.select_related('guest', 'property').prefetch_related(
        'booking_rooms__room', 'booking_rooms__room_type', 'booking_rooms__rate_plan'
    ).all()
    serializer_class = BookingSerializer
    filterset_fields = ['property', 'status', 'source', 'guest']

    def create(self, request, *args, **kwargs):
        input_serializer = BookingCreateSerializer(data=request.data)
        input_serializer.is_valid(raise_exception=True)
        data = input_serializer.validated_data

        property_obj = get_object_or_404(Property, id=data['property'])
        guest = get_object_or_404(Guest, id=data['guest'])

        try:
            booking = create_booking(
                property_obj=property_obj,
                guest=guest,
                check_in_date=data['check_in_date'],
                check_out_date=data['check_out_date'],
                room_requests=data['rooms'],
                source=data['source'],
                adults=data['adults'],
                children=data['children'],
                special_requests=data['special_requests'],
            )
        except RoomNotAvailableError as e:
            return Response({'detail': str(e)}, status=status.HTTP_409_CONFLICT)
        except ValidationError as e:
            return Response({'detail': str(e)}, status=status.HTTP_400_BAD_REQUEST)

        return Response(BookingSerializer(booking).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['post'])
    def cancel(self, request, pk=None):
        """POST /api/bookings/{id}/cancel/ — releases the room inventory back."""
        booking = self.get_object()
        if booking.status == Booking.Status.CANCELLED:
            return Response({'detail': 'Booking is already cancelled.'}, status=400)

        from django.utils import timezone
        from apps.availability.models import Availability

        Availability.objects.filter(
            booking_room__booking=booking
        ).update(is_available=True, booking_room=None)

        booking.status = Booking.Status.CANCELLED
        booking.cancelled_at = timezone.now()
        booking.cancellation_reason = request.data.get('reason', '')
        booking.save(update_fields=['status', 'cancelled_at', 'cancellation_reason', 'updated_at'])

        return Response(BookingSerializer(booking).data)