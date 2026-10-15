from django.contrib import admin
from .models import Inquiry


@admin.register(Inquiry)
class InquiryAdmin(admin.ModelAdmin):
    list_display = ('created_at', 'name', 'phone', 'email', 'hotel', 'status')
    list_editable = ('status',)
    list_filter = ('status', 'hotel', 'created_at')
    search_fields = ('name', 'email', 'phone', 'comment')
    date_hierarchy = 'created_at'
    ordering = ('-created_at',)
    actions = ['mark_contacted', 'mark_closed']

    fields = ('status', 'admin_notes', 'name', 'email', 'phone', 'hotel',
              'comment', 'source_page', 'ip_address', 'created_at')
    # What the guest wrote stays exactly as submitted; staff only change status and notes.
    readonly_fields = ('name', 'email', 'phone', 'hotel', 'comment',
                       'source_page', 'ip_address', 'created_at')

    def has_add_permission(self, request):
        return False   # enquiries only come from the website form

    @admin.action(description='Mark selected as contacted')
    def mark_contacted(self, request, queryset):
        queryset.update(status=Inquiry.Status.CONTACTED)

    @admin.action(description='Mark selected as closed')
    def mark_closed(self, request, queryset):
        queryset.update(status=Inquiry.Status.CLOSED)