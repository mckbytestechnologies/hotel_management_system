from django.contrib import admin
from .models import ChannelMapping, SyncLog


@admin.register(ChannelMapping)
class ChannelMappingAdmin(admin.ModelAdmin):
    list_display = ('property', 'room_type', 'rate_plan', 'staah_property_id', 'staah_room_id', 'staah_rate_plan_id')
    list_filter = ('property',)
    search_fields = ('staah_property_id', 'staah_room_id', 'staah_rate_plan_id')
    list_select_related = ('property', 'room_type', 'rate_plan')


@admin.register(SyncLog)
class SyncLogAdmin(admin.ModelAdmin):
    list_display = ('property', 'sync_type', 'direction', 'status', 'created_at')
    list_filter = ('sync_type', 'direction', 'status', 'property')
    readonly_fields = ('created_at', 'updated_at', 'request_payload', 'response_payload')
    list_select_related = ('property',)
    date_hierarchy = 'created_at'