from django.contrib import admin
from .models import StaffProfile, StaffPermission


class StaffPermissionInline(admin.TabularInline):
    """
    Lets the Admin grant module-by-module access directly on the
    StaffProfile edit page — no need to jump to a separate screen.
    """
    model = StaffPermission
    extra = 1


@admin.register(StaffProfile)
class StaffProfileAdmin(admin.ModelAdmin):
    list_display = ('user', 'employee_code', 'property', 'phone', 'is_active', 'created_at')
    list_filter = ('is_active', 'property')
    search_fields = ('user__username', 'user__first_name', 'user__last_name', 'employee_code')
    inlines = [StaffPermissionInline]
    readonly_fields = ('created_at', 'updated_at')


@admin.register(StaffPermission)
class StaffPermissionAdmin(admin.ModelAdmin):
    list_display = ('staff', 'module', 'can_view', 'can_add', 'can_edit', 'can_delete')
    list_filter = ('module', 'can_view', 'can_add', 'can_edit', 'can_delete')
    search_fields = ('staff__user__username',)