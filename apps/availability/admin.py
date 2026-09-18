from django.contrib import admin
from .models import RoomRate, SeasonalRate, Restriction, Availability


@admin.register(RoomRate)
class RoomRateAdmin(admin.ModelAdmin):
    list_display = ('room_type', 'rate_plan', 'date', 'base_price', 'is_active')
    list_filter = ('property', 'room_type', 'rate_plan')
    search_fields = ('room_type__name', 'rate_plan__name')
    date_hierarchy = 'date'
    list_select_related = ('room_type', 'rate_plan', 'property')  # avoids N+1 in admin list


@admin.register(SeasonalRate)
class SeasonalRateAdmin(admin.ModelAdmin):
    list_display = ('name', 'room_type', 'rate_plan', 'start_date', 'end_date', 'adjustment_type', 'adjustment_value')
    list_filter = ('property', 'adjustment_type')
    list_select_related = ('room_type', 'rate_plan', 'property')


@admin.register(Restriction)
class RestrictionAdmin(admin.ModelAdmin):
    list_display = ('room_type', 'rate_plan', 'date', 'min_stay', 'closed_to_arrival', 'stop_sell')
    list_filter = ('property', 'stop_sell', 'closed_to_arrival', 'closed_to_departure')
    date_hierarchy = 'date'
    list_select_related = ('room_type', 'rate_plan', 'property')


@admin.register(Availability)
class AvailabilityAdmin(admin.ModelAdmin):
    list_display = ('room', 'date', 'is_available', 'is_blocked', 'block_reason')
    list_filter = ('property', 'is_available', 'is_blocked')
    date_hierarchy = 'date'
    list_select_related = ('room', 'property')