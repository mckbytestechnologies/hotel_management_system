from rest_framework import serializers
from .models import Property, RoomType, Room, RatePlan


class PropertySerializer(serializers.ModelSerializer):
    class Meta:
        model = Property
        fields = [
            'id', 'name', 'code', 'address', 'city', 'state', 'country',
            'phone', 'email', 'check_in_time', 'check_out_time',
            'tax_number', 'is_active', 'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']


class RoomTypeSerializer(serializers.ModelSerializer):
    property_name = serializers.CharField(source='property.name', read_only=True)

    class Meta:
        model = RoomType
        fields = [
            'id', 'property', 'property_name', 'name', 'code', 'description',
            'max_adults', 'max_children', 'max_occupancy', 'base_occupancy',
            'is_active', 'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']


class RoomSerializer(serializers.ModelSerializer):
    room_type_name = serializers.CharField(source='room_type.name', read_only=True)
    property_name = serializers.CharField(source='property.name', read_only=True)

    class Meta:
        model = Room
        fields = [
            'id', 'property', 'property_name', 'room_type', 'room_type_name',
            'room_number', 'floor', 'status', 'is_active',
            'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']

    def validate(self, data):
        """
        Ensure the room_type belongs to the same property as the room.
        Prevents assigning a RoomType from Property A to a Room under Property B.
        """
        room_type = data.get('room_type') or getattr(self.instance, 'room_type', None)
        property_ = data.get('property') or getattr(self.instance, 'property', None)
        if room_type and property_ and room_type.property_id != property_.id:
            raise serializers.ValidationError(
                "Room type does not belong to the selected property."
            )
        return data


class RatePlanSerializer(serializers.ModelSerializer):
    property_name = serializers.CharField(source='property.name', read_only=True)

    class Meta:
        model = RatePlan
        fields = [
            'id', 'property', 'property_name', 'name', 'code', 'description',
            'meal_plan', 'cancellation_policy', 'is_refundable', 'is_active',
            'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']