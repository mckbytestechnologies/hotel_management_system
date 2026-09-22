from django.urls import reverse_lazy
from apps.core.models import Module
from apps.properties.models import Property, RoomType, Room, RatePlan
from apps.properties.forms import PropertyForm, RoomTypeForm, RoomForm, RatePlanForm
from .generic_views import BaseListView, BaseCreateView, BaseUpdateView, BaseDeleteView
import calendar
from datetime import date
from django.db.models import Count
from django.contrib.auth.mixins import LoginRequiredMixin
from django.views.generic import TemplateView

from apps.bookings.models import Booking
from apps.bookings.forms import BookingForm
from datetime import timedelta
from django.shortcuts import redirect
from django.views.generic import TemplateView
from apps.core.mixins import ModulePermissionRequiredMixin
from apps.availability.models import RoomRate
from apps.availability.forms import RoomRateForm, BulkRateForm
from django.contrib import messages
from apps.bookings.services import check_in_booking, check_out_booking, InvalidBookingStateError
from django.views.decorators.http import require_POST
from django.utils.decorators import method_decorator
from django.views import View
from apps.bookings.models import Payment, Invoice

from apps.integrations.models import ChannelMapping, SyncLog

class DashboardHomeView(LoginRequiredMixin, TemplateView):
    template_name = 'dashboard/home.html'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)

        # --- Live counts from what's built so far ---
        context['total_properties'] = Property.objects.filter(is_active=True).count()
        context['total_room_types'] = RoomType.objects.filter(is_active=True).count()
        context['total_rooms'] = Room.objects.filter(is_active=True).count()
        context['total_rate_plans'] = RatePlan.objects.filter(is_active=True).count()

        # --- Room status breakdown (for the little bar chart) ---
        status_counts = (
            Room.objects.filter(is_active=True)
            .values('status')
            .annotate(count=Count('id'))
        )
        status_map = {row['status']: row['count'] for row in status_counts}
        total_rooms = context['total_rooms'] or 1  # avoid divide-by-zero
        context['room_status_breakdown'] = [
            {
                'label': label,
                'value': value,
                'count': status_map.get(value, 0),
                'percent': round((status_map.get(value, 0) / total_rooms) * 100),
            }
            for value, label in Room.RoomStatus.choices
        ]

        # --- Bookings/occupancy: placeholders until `bookings` app is built ---
        # TODO: replace with real Booking.objects queries once that app exists.
        context['todays_checkins'] = 0
        context['todays_checkouts'] = 0
        context['active_bookings'] = 0
        context['occupancy_percent'] = 0

        # --- Simple current-month calendar (Python's calendar module) ---
        today = date.today()
        cal = calendar.Calendar(firstweekday=6)  # Sunday first
        month_days = cal.monthdayscalendar(today.year, today.month)
        context['calendar_weeks'] = month_days
        context['calendar_month_name'] = today.strftime('%B %Y')
        context['today_day'] = today.day

        return context

class PropertyListView(BaseListView):
    module = Module.PROPERTIES
    model = Property
    ordering = ['name']
    page_title = 'Properties'
    singular_name = 'Property'
    add_url_name = 'dashboard:property_add'
    edit_url_name = 'dashboard:property_edit'
    delete_url_name = 'dashboard:property_delete'
    columns = [
        {'label': 'Name', 'field': 'name'},
        {'label': 'Code', 'field': 'code'},
        {'label': 'City', 'field': 'city'},
        {'label': 'Country', 'field': 'country'},
        {'label': 'Status', 'field': 'is_active', 'badge': True},
    ]


class PropertyCreateView(BaseCreateView):
    module = Module.PROPERTIES
    model = Property
    form_class = PropertyForm
    page_title = 'Add Property'
    success_message = 'Property created successfully.'
    success_url = reverse_lazy('dashboard:property_list')


class PropertyUpdateView(BaseUpdateView):
    module = Module.PROPERTIES
    model = Property
    form_class = PropertyForm
    page_title = 'Edit Property'
    success_message = 'Property updated successfully.'
    success_url = reverse_lazy('dashboard:property_list')


class PropertyDeleteView(BaseDeleteView):
    module = Module.PROPERTIES
    model = Property
    success_url = reverse_lazy('dashboard:property_list')


class RoomTypeListView(BaseListView):
    module = Module.ROOM_TYPES
    model = RoomType
    ordering = ['property', 'name']
    page_title = 'Room Types'
    singular_name = 'Room Type'
    add_url_name = 'dashboard:roomtype_add'
    edit_url_name = 'dashboard:roomtype_edit'
    delete_url_name = 'dashboard:roomtype_delete'
    columns = [
        {'label': 'Name', 'field': 'name'},
        {'label': 'Code', 'field': 'code'},
        {'label': 'Property', 'field': 'property.name'},
        {'label': 'Max Occupancy', 'field': 'max_occupancy'},
        {'label': 'Status', 'field': 'is_active', 'badge': True},
    ]


class RoomTypeCreateView(BaseCreateView):
    module = Module.ROOM_TYPES
    model = RoomType
    form_class = RoomTypeForm
    page_title = 'Add Room Type'
    success_message = 'Room type created successfully.'
    success_url = reverse_lazy('dashboard:roomtype_list')


class RoomTypeUpdateView(BaseUpdateView):
    module = Module.ROOM_TYPES
    model = RoomType
    form_class = RoomTypeForm
    page_title = 'Edit Room Type'
    success_message = 'Room type updated successfully.'
    success_url = reverse_lazy('dashboard:roomtype_list')


class RoomTypeDeleteView(BaseDeleteView):
    module = Module.ROOM_TYPES
    model = RoomType
    success_url = reverse_lazy('dashboard:roomtype_list')

class RoomListView(BaseListView):
    module = Module.ROOMS
    model = Room
    ordering = ['property', 'room_type', 'room_number']
    page_title = 'Rooms'
    singular_name = 'Room'
    add_url_name = 'dashboard:room_add'
    edit_url_name = 'dashboard:room_edit'
    delete_url_name = 'dashboard:room_delete'
    columns = [
        {'label': 'Room Number', 'field': 'room_number'},
        {'label': 'Room Type', 'field': 'room_type.name'},
        {'label': 'Property', 'field': 'property.name'},
        {'label': 'Floor', 'field': 'floor'},
        {'label': 'Status', 'field': 'status'},
    ]


class RoomCreateView(BaseCreateView):
    module = Module.ROOMS
    model = Room
    form_class = RoomForm
    page_title = 'Add Room'
    success_message = 'Room created successfully.'
    success_url = reverse_lazy('dashboard:room_list')


class RoomUpdateView(BaseUpdateView):
    module = Module.ROOMS
    model = Room
    form_class = RoomForm
    page_title = 'Edit Room'
    success_message = 'Room updated successfully.'
    success_url = reverse_lazy('dashboard:room_list')


class RoomDeleteView(BaseDeleteView):
    module = Module.ROOMS
    model = Room
    success_url = reverse_lazy('dashboard:room_list')


class RatePlanListView(BaseListView):
    module = Module.RATE_PLANS
    model = RatePlan
    ordering = ['property', 'name']
    page_title = 'Rate Plans'
    singular_name = 'Rate Plan'
    add_url_name = 'dashboard:rateplan_add'
    edit_url_name = 'dashboard:rateplan_edit'
    delete_url_name = 'dashboard:rateplan_delete'
    columns = [
        {'label': 'Name', 'field': 'name'},
        {'label': 'Code', 'field': 'code'},
        {'label': 'Property', 'field': 'property.name'},
        {'label': 'Meal Plan', 'field': 'meal_plan'},
        {'label': 'Refundable', 'field': 'is_refundable', 'badge': True},
    ]


class RatePlanCreateView(BaseCreateView):
    module = Module.RATE_PLANS
    model = RatePlan
    form_class = RatePlanForm
    page_title = 'Add Rate Plan'
    success_message = 'Rate plan created successfully.'
    success_url = reverse_lazy('dashboard:rateplan_list')


class RatePlanUpdateView(BaseUpdateView):
    module = Module.RATE_PLANS
    model = RatePlan
    form_class = RatePlanForm
    page_title = 'Edit Rate Plan'
    success_message = 'Rate plan updated successfully.'
    success_url = reverse_lazy('dashboard:rateplan_list')


class RatePlanDeleteView(BaseDeleteView):
    module = Module.RATE_PLANS
    model = RatePlan
    success_url = reverse_lazy('dashboard:rateplan_list')


class BookingListView(BaseListView):
    module = Module.BOOKINGS
    model = Booking
    ordering = ['-created_at']
    page_title = 'Bookings'
    singular_name = 'Booking'
    add_url_name = None  # bookings are created via the public site / dedicated flow, not this form
    edit_url_name = 'dashboard:booking_edit'
    delete_url_name = None  # bookings are cancelled, not deleted — see BookingCancelView below
    columns = [
        {'label': 'Booking #', 'field': 'booking_number'},
        {'label': 'Guest', 'field': 'guest.full_name'},
        {'label': 'Property', 'field': 'property.name'},
        {'label': 'Check-in', 'field': 'check_in_date'},
        {'label': 'Check-out', 'field': 'check_out_date'},
        {'label': 'Status', 'field': 'status'},
        {'label': 'Total', 'field': 'total_amount'},
    ]

    def get_queryset(self):
        return super().get_queryset().select_related('guest', 'property')


class BookingUpdateView(BaseUpdateView):
    module = Module.BOOKINGS
    model = Booking
    form_class = BookingForm
    page_title = 'Edit Booking'
    success_message = 'Booking updated successfully.'
    success_url = reverse_lazy('dashboard:booking_list')


class RoomRateListView(BaseListView):
    module = Module.AVAILABILITY
    model = RoomRate
    ordering = ['-date']
    page_title = 'Room Rates'
    singular_name = 'Room Rate'
    add_url_name = 'dashboard:roomrate_add'
    edit_url_name = 'dashboard:roomrate_edit'
    delete_url_name = 'dashboard:roomrate_delete'
    columns = [
        {'label': 'Date', 'field': 'date'},
        {'label': 'Room Type', 'field': 'room_type.name'},
        {'label': 'Rate Plan', 'field': 'rate_plan.name'},
        {'label': 'Base Price', 'field': 'base_price'},
        {'label': 'Active', 'field': 'is_active', 'badge': True},
    ]

    def get_queryset(self):
        return super().get_queryset().select_related('room_type', 'rate_plan', 'property')


class RoomRateCreateView(BaseCreateView):
    module = Module.AVAILABILITY
    model = RoomRate
    form_class = RoomRateForm
    page_title = 'Add Room Rate'
    success_message = 'Room rate created successfully.'
    success_url = reverse_lazy('dashboard:roomrate_list')


class RoomRateUpdateView(BaseUpdateView):
    module = Module.AVAILABILITY
    model = RoomRate
    form_class = RoomRateForm
    page_title = 'Edit Room Rate'
    success_message = 'Room rate updated successfully.'
    success_url = reverse_lazy('dashboard:roomrate_list')


class RoomRateDeleteView(BaseDeleteView):
    module = Module.AVAILABILITY
    model = RoomRate
    success_url = reverse_lazy('dashboard:roomrate_list')


class BulkRateGenerateView(ModulePermissionRequiredMixin, TemplateView):
    module = Module.AVAILABILITY
    permission_action = 'add'
    template_name = 'dashboard/room_rates/bulk_form.html'

    def get(self, request):
        return self.render_to_response({'form': BulkRateForm()})

    def post(self, request):
        form = BulkRateForm(request.POST)
        if not form.is_valid():
            return self.render_to_response({'form': form})

        data = form.cleaned_data
        date_range = [
            data['start_date'] + timedelta(days=i)
            for i in range((data['end_date'] - data['start_date']).days + 1)
        ]

        created, updated = 0, 0
        for d in date_range:
            obj, was_created = RoomRate.objects.update_or_create(
                property=data['property'],
                room_type=data['room_type'],
                rate_plan=data['rate_plan'],
                date=d,
                defaults={'base_price': data['base_price']},
            )
            created += was_created
            updated += (not was_created)

        messages.success(
            request,
            f"Rates set for {len(date_range)} dates ({created} created, {updated} updated)."
        )
        return redirect('dashboard:roomrate_list')

@method_decorator(require_POST, name='dispatch')
class BookingCheckInView(ModulePermissionRequiredMixin, View):
    module = Module.BOOKINGS
    permission_action = 'edit'

    def post(self, request, pk):
        try:
            check_in_booking(pk)
            messages.success(request, 'Guest checked in successfully.')
        except InvalidBookingStateError as e:
            messages.error(request, str(e))
        return redirect('dashboard:booking_list')


@method_decorator(require_POST, name='dispatch')
class BookingCheckOutView(ModulePermissionRequiredMixin, View):
    module = Module.BOOKINGS
    permission_action = 'edit'

    def post(self, request, pk):
        try:
            check_out_booking(pk)
            messages.success(request, 'Guest checked out successfully.')
        except InvalidBookingStateError as e:
            messages.error(request, str(e))
        return redirect('dashboard:booking_list')

class PaymentListView(BaseListView):
    module = Module.PAYMENTS
    model = Payment
    ordering = ['-created_at']
    page_title = 'Payments'
    singular_name = 'Payment'
    add_url_name = None  # payments are created via booking/checkout flow, not manually here
    edit_url_name = None  # payments are immutable records — status changes via refund flow instead
    delete_url_name = None
    columns = [
        {'label': 'Booking #', 'field': 'booking.booking_number'},
        {'label': 'Guest', 'field': 'booking.guest.full_name'},
        {'label': 'Amount', 'field': 'amount'},
        {'label': 'Method', 'field': 'method'},
        {'label': 'Status', 'field': 'status'},
        {'label': 'Reference', 'field': 'transaction_reference'},
        {'label': 'Paid At', 'field': 'paid_at'},
    ]

    def get_queryset(self):
        return super().get_queryset().select_related('booking', 'booking__guest')


class InvoiceListView(BaseListView):
    module = Module.PAYMENTS
    model = Invoice
    ordering = ['-issued_at']
    page_title = 'Invoices'
    singular_name = 'Invoice'
    view_url_name = 'dashboard:invoice_view'
    add_url_name = None  # invoices are generated automatically, not manually created
    edit_url_name = None
    delete_url_name = None
    columns = [
        {'label': 'Invoice #', 'field': 'invoice_number'},
        {'label': 'Booking #', 'field': 'booking.booking_number'},
        {'label': 'Guest', 'field': 'booking.guest.full_name'},
        {'label': 'Subtotal', 'field': 'subtotal'},
        {'label': 'Total', 'field': 'total_amount'},
        {'label': 'Issued', 'field': 'issued_at'},
    ]

    def get_queryset(self):
        return super().get_queryset().select_related('booking', 'booking__guest')

from django.shortcuts import get_object_or_404, render
from apps.bookings.services import generate_invoice


class InvoiceViewByPk(ModulePermissionRequiredMixin, View):
    """
    Dashboard-side invoice viewer, keyed by Invoice pk (matches the
    generic list's obj.pk convention) rather than booking_number
    (used by the public-facing view_invoice).
    """
    module = Module.PAYMENTS
    permission_action = 'view'

    def get(self, request, pk):
        invoice = get_object_or_404(Invoice, pk=pk)
        return render(request, 'public/invoice.html', {
            'booking': invoice.booking,
            'invoice': invoice,
        })

class SyncLogListView(BaseListView):
    module = Module.INTEGRATIONS
    model = SyncLog
    ordering = ['-created_at']
    page_title = 'STAAH Sync Logs'
    singular_name = 'Sync Log'
    add_url_name = None
    edit_url_name = None
    delete_url_name = None
    columns = [
        {'label': 'Property', 'field': 'property.name'},
        {'label': 'Type', 'field': 'sync_type'},
        {'label': 'Direction', 'field': 'direction'},
        {'label': 'Status', 'field': 'status'},
        {'label': 'Time', 'field': 'created_at'},
        {'label': 'Error', 'field': 'error_message'},
    ]

    def get_queryset(self):
        return super().get_queryset().select_related('property')


class ChannelMappingListView(BaseListView):
    module = Module.INTEGRATIONS
    model = ChannelMapping
    ordering = ['property']
    page_title = 'STAAH Channel Mappings'
    singular_name = 'Channel Mapping'
    add_url_name = 'dashboard:channelmapping_add'
    edit_url_name = 'dashboard:channelmapping_edit'
    delete_url_name = 'dashboard:channelmapping_delete'
    columns = [
        {'label': 'Property', 'field': 'property.name'},
        {'label': 'Room Type', 'field': 'room_type.name'},
        {'label': 'Rate Plan', 'field': 'rate_plan.name'},
        {'label': 'STAAH Property ID', 'field': 'staah_property_id'},
        {'label': 'STAAH Room ID', 'field': 'staah_room_id'},
    ]

    def get_queryset(self):
        return super().get_queryset().select_related('property', 'room_type', 'rate_plan')


class ChannelMappingCreateView(BaseCreateView):
    module = Module.INTEGRATIONS
    model = ChannelMapping
    fields = ['property', 'room_type', 'rate_plan', 'staah_property_id', 'staah_room_id', 'staah_rate_plan_id']
    page_title = 'Add Channel Mapping'
    success_message = 'Channel mapping created successfully.'
    success_url = reverse_lazy('dashboard:channelmapping_list')


class ChannelMappingUpdateView(BaseUpdateView):
    module = Module.INTEGRATIONS
    model = ChannelMapping
    fields = ['property', 'room_type', 'rate_plan', 'staah_property_id', 'staah_room_id', 'staah_rate_plan_id']
    page_title = 'Edit Channel Mapping'
    success_message = 'Channel mapping updated successfully.'
    success_url = reverse_lazy('dashboard:channelmapping_list')


class ChannelMappingDeleteView(BaseDeleteView):
    module = Module.INTEGRATIONS
    model = ChannelMapping
    success_url = reverse_lazy('dashboard:channelmapping_list')