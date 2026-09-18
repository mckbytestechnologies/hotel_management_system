from django.contrib import admin
from .models import Booking, BookingRoom


class BookingRoomInline(admin.TabularInline):
    model = BookingRoom
    extra = 1
    readonly_fields = ('created_at', 'updated_at')


@admin.register(Booking)
class BookingAdmin(admin.ModelAdmin):
    list_display = (
        'booking_number', 'guest', 'property', 'check_in_date', 'check_out_date',
        'status', 'source', 'total_amount', 'paid_amount',
    )
    list_filter = ('status', 'source', 'property')
    search_fields = ('booking_number', 'guest__first_name', 'guest__last_name', 'guest__phone', 'ota_reference')
    date_hierarchy = 'check_in_date'
    list_select_related = ('guest', 'property')
    inlines = [BookingRoomInline]
    readonly_fields = ('created_at', 'updated_at')


@admin.register(BookingRoom)
class BookingRoomAdmin(admin.ModelAdmin):
    list_display = ('booking', 'room', 'room_type', 'rate_plan', 'check_in_date', 'check_out_date', 'rate_amount')
    list_filter = ('room_type', 'rate_plan')
    list_select_related = ('booking', 'room', 'room_type', 'rate_plan')