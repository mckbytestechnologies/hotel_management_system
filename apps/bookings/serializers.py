from rest_framework import serializers
from .models import Booking, BookingRoom


class BookingRoomInputSerializer(serializers.Serializer):
    """Shapes one room request inside a booking creation payload."""
    room_id = serializers.IntegerField()
    room_type_id = serializers.IntegerField()
    rate_plan_id = serializers.IntegerField()
    adults = serializers.IntegerField(default=1)
    children = serializers.IntegerField(default=0)


class BookingRoomSerializer(serializers.ModelSerializer):
    room_number = serializers.CharField(source='room.room_number', read_only=True)
    room_type_name = serializers.CharField(source='room_type.name', read_only=True)
    rate_plan_name = serializers.CharField(source='rate_plan.name', read_only=True)

    class Meta:
        model = BookingRoom
        fields = [
            'id', 'room', 'room_number', 'room_type', 'room_type_name',
            'rate_plan', 'rate_plan_name', 'check_in_date', 'check_out_date',
            'rate_amount', 'adults', 'children',
        ]


class BookingSerializer(serializers.ModelSerializer):
    """Read serializer — includes nested rooms."""
    guest_name = serializers.CharField(source='guest.full_name', read_only=True)
    property_name = serializers.CharField(source='property.name', read_only=True)
    booking_rooms = BookingRoomSerializer(many=True, read_only=True)
    nights = serializers.SerializerMethodField()
    balance_due = serializers.SerializerMethodField()

    class Meta:
        model = Booking
        fields = [
            'id', 'booking_number', 'property', 'property_name', 'guest', 'guest_name',
            'check_in_date', 'check_out_date', 'nights', 'status', 'source',
            'adults', 'children', 'special_requests',
            'total_amount', 'paid_amount', 'balance_due',
            'ota_reference', 'cancelled_at', 'cancellation_reason',
            'booking_rooms', 'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'booking_number', 'total_amount', 'created_at', 'updated_at']

    def get_nights(self, obj):
        return obj.nights()

    def get_balance_due(self, obj):
        return obj.balance_due()


class BookingCreateSerializer(serializers.Serializer):
    """Write serializer for POST /api/bookings/ — feeds create_booking()."""
    property = serializers.IntegerField()
    guest = serializers.IntegerField()
    check_in_date = serializers.DateField()
    check_out_date = serializers.DateField()
    source = serializers.ChoiceField(choices=Booking.Source.choices, default=Booking.Source.DIRECT)
    adults = serializers.IntegerField(default=1)
    children = serializers.IntegerField(default=0)
    special_requests = serializers.CharField(required=False, allow_blank=True, default='')
    rooms = BookingRoomInputSerializer(many=True)

    def validate_rooms(self, value):
        if not value:
            raise serializers.ValidationError("At least one room is required.")
        return value