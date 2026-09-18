from rest_framework import serializers
from .models import RoomRate, SeasonalRate, Restriction, Availability


class RoomRateSerializer(serializers.ModelSerializer):
    room_type_name = serializers.CharField(source='room_type.name', read_only=True)
    rate_plan_name = serializers.CharField(source='rate_plan.name', read_only=True)

    class Meta:
        model = RoomRate
        fields = [
            'id', 'property', 'room_type', 'room_type_name', 'rate_plan', 'rate_plan_name',
            'date', 'base_price', 'extra_adult_price', 'extra_child_price',
            'is_active', 'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']


class SeasonalRateSerializer(serializers.ModelSerializer):
    class Meta:
        model = SeasonalRate
        fields = [
            'id', 'property', 'room_type', 'rate_plan', 'name',
            'start_date', 'end_date', 'adjustment_type', 'adjustment_value',
            'is_active', 'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']

    def validate(self, data):
        start = data.get('start_date') or getattr(self.instance, 'start_date', None)
        end = data.get('end_date') or getattr(self.instance, 'end_date', None)
        if start and end and end < start:
            raise serializers.ValidationError("end_date cannot be before start_date.")
        return data


class RestrictionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Restriction
        fields = [
            'id', 'property', 'room_type', 'rate_plan', 'date',
            'min_stay', 'max_stay', 'closed_to_arrival', 'closed_to_departure',
            'stop_sell', 'is_active', 'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']


class AvailabilitySerializer(serializers.ModelSerializer):
    room_number = serializers.CharField(source='room.room_number', read_only=True)

    class Meta:
        model = Availability
        fields = [
            'id', 'property', 'room', 'room_number', 'date',
            'is_available', 'is_blocked', 'block_reason',
            'is_active', 'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']


class AvailabilitySearchResultSerializer(serializers.Serializer):
    """
    Not a ModelSerializer — this shapes the output of the search endpoint,
    which aggregates across RoomType + RoomRate + Restriction + Availability,
    not a single model. Kept lightweight on purpose (search is the highest-
    traffic endpoint in the system).
    """
    room_type_id = serializers.IntegerField()
    room_type_name = serializers.CharField()
    rate_plan_id = serializers.IntegerField()
    rate_plan_name = serializers.CharField()
    available_rooms = serializers.IntegerField()
    total_price = serializers.DecimalField(max_digits=10, decimal_places=2)
    nightly_avg_price = serializers.DecimalField(max_digits=10, decimal_places=2)
    min_stay = serializers.IntegerField()
    is_bookable = serializers.BooleanField()