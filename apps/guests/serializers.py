from rest_framework import serializers
from .models import Guest


class GuestSerializer(serializers.ModelSerializer):
    full_name = serializers.CharField(read_only=True)

    class Meta:
        model = Guest
        fields = [
            'id', 'first_name', 'last_name', 'full_name', 'email', 'phone',
            'id_proof_type', 'id_proof_number', 'nationality',
            'address', 'city', 'country', 'date_of_birth', 'notes',
            'is_active', 'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']