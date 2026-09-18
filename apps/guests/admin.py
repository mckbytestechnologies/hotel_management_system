from django.contrib import admin
from .models import Guest


@admin.register(Guest)
class GuestAdmin(admin.ModelAdmin):
    list_display = ('full_name', 'email', 'phone', 'nationality', 'city', 'is_active', 'created_at')
    list_filter = ('is_active', 'nationality', 'country')
    search_fields = ('first_name', 'last_name', 'email', 'phone', 'id_proof_number')
    readonly_fields = ('created_at', 'updated_at')