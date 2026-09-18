from rest_framework import viewsets, filters
from django_filters.rest_framework import DjangoFilterBackend
from .models import Guest
from .serializers import GuestSerializer


class GuestViewSet(viewsets.ModelViewSet):
    queryset = Guest.objects.all()
    serializer_class = GuestSerializer
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['is_active', 'nationality', 'country']
    search_fields = ['first_name', 'last_name', 'email', 'phone', 'id_proof_number']
    ordering_fields = ['first_name', 'created_at']