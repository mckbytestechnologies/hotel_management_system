from django.contrib import admin
from .models import Property, RoomType, Room, RatePlan


@admin.register(Property)
class PropertyAdmin(admin.ModelAdmin):
    list_display = ('name', 'code', 'city', 'country', 'is_active', 'created_at')
    list_filter = ('is_active', 'country', 'city')
    search_fields = ('name', 'code', 'city')
    ordering = ('name',)
    readonly_fields = ('created_at', 'updated_at')


@admin.register(RoomType)
class RoomTypeAdmin(admin.ModelAdmin):
    list_display = ('name', 'code', 'property', 'max_occupancy', 'is_active')
    list_filter = ('is_active', 'property')
    search_fields = ('name', 'code')
    ordering = ('property', 'name')
    readonly_fields = ('created_at', 'updated_at')


@admin.register(Room)
class RoomAdmin(admin.ModelAdmin):
    list_display = ('room_number', 'room_type', 'property', 'floor', 'status', 'is_active')
    list_filter = ('status', 'is_active', 'property', 'room_type')
    search_fields = ('room_number',)
    ordering = ('property', 'room_type', 'room_number')
    readonly_fields = ('created_at', 'updated_at')


@admin.register(RatePlan)
class RatePlanAdmin(admin.ModelAdmin):
    list_display = ('name', 'code', 'property', 'meal_plan', 'is_refundable', 'is_active')
    list_filter = ('is_refundable', 'is_active', 'property')
    search_fields = ('name', 'code')
    ordering = ('property', 'name')
    readonly_fields = ('created_at', 'updated_at')