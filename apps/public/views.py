from datetime import date, timedelta
from django.shortcuts import render, redirect
from django.contrib import messages
from apps.properties.models import Property
from datetime import date as date_cls
from apps.properties.models import RoomType, Room, RatePlan
from apps.availability.models import RoomRate, Availability, Restriction
from apps.properties.models import Property, RoomType, Room, RatePlan
from django.db.models import Count, Q
from apps.guests.models import Guest
from apps.bookings.services import create_booking, RoomNotAvailableError
from django.core.exceptions import ValidationError
from datetime import timedelta
import json
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from django.core.mail import send_mail
from django.conf import settings
from apps.guests.models import EmailOTP


def landing_page(request):
    """
    The public homepage: a hero search form (property, check-in, check-out,
    guests). Submitting redirects to the search results page with these
    as query params — keeps the results page bookmarkable/shareable.
    """
    properties = Property.objects.filter(is_active=True)

    if request.method == 'POST':
        property_id = request.POST.get('property')
        check_in = request.POST.get('check_in')
        check_out = request.POST.get('check_out')
        adults = request.POST.get('adults', 1)

        if not all([property_id, check_in, check_out]):
            messages.error(request, 'Please select a property and both dates.')
            return redirect('public:landing')

        return redirect(
            f"/book/search/?property={property_id}&check_in={check_in}"
            f"&check_out={check_out}&adults={adults}"
        )

    today = date.today()
    default_checkin = today + timedelta(days=1)
    default_checkout = today + timedelta(days=2)

    return render(request, 'public/landing.html', {
        'properties': properties,

        # Default values
        'default_checkin': default_checkin.isoformat(),
        'default_checkout': default_checkout.isoformat(),

        # Minimum selectable dates
        'min_checkin': today.isoformat(),
        'min_checkout': (today + timedelta(days=1)).isoformat(),
    })

def search_results(request):
    """
    Public search results page. Reuses the exact same availability
    calculation logic as the internal AvailabilitySearchView API —
    kept as a separate, simpler inline version here since this page
    needs full Property/RoomType objects (for images/descriptions)
    rather than the lightweight JSON shape the API returns.
    """
    property_id = request.GET.get('property')
    check_in = request.GET.get('check_in')
    check_out = request.GET.get('check_out')
    adults = request.GET.get('adults', 1)

    if not all([property_id, check_in, check_out]):
        messages.error(request, 'Please select a property and both dates.')
        return redirect('public:landing')

    try:
        check_in_date = date_cls.fromisoformat(check_in)
        check_out_date = date_cls.fromisoformat(check_out)
    except ValueError:
        messages.error(request, 'Invalid dates provided.')
        return redirect('public:landing')

    today = date_cls.today()

    if check_in_date < today:
        messages.error(request, 'Check-in date cannot be in the past.')
        return redirect('public:landing')

    if check_out_date <= check_in_date:
        messages.error(request, 'Check-out must be after check-in.')
        return redirect('public:landing')

    property_obj = Property.objects.filter(id=property_id, is_active=True).first()
    if not property_obj:
        messages.error(request, 'Selected property not found.')
        return redirect('public:landing')

    nights = (check_out_date - check_in_date).days
    from datetime import timedelta
    stay_dates = [check_in_date + timedelta(days=i) for i in range(nights)]

    room_types = RoomType.objects.filter(property=property_obj, is_active=True)

    blocked_room_ids = set(
        Availability.objects.filter(date__in=stay_dates)
        .filter(Q(is_available=False) | Q(is_blocked=True))
        .values_list('room_id', flat=True).distinct()
    )

    rate_plans = RatePlan.objects.filter(property=property_obj, is_active=True)

    rates_qs = RoomRate.objects.filter(
        property=property_obj, date__in=stay_dates
    ).values('room_type_id', 'rate_plan_id', 'date', 'base_price')

    rates_by_combo = {}
    for row in rates_qs:
        key = (row['room_type_id'], row['rate_plan_id'])
        rates_by_combo.setdefault(key, {})[row['date']] = row['base_price']

    results = []
    for rt in room_types:
        rt_room_ids = set(Room.objects.filter(room_type=rt, is_active=True).values_list('id', flat=True))
        free_rooms_count = len(rt_room_ids - blocked_room_ids)
        if free_rooms_count == 0:
            continue

        # for plan in rate_plans:
        #     key = (rt.id, plan.id)
        #     nightly_rates = rates_by_combo.get(key, {})
        #     if len(nightly_rates) < nights:
        #         continue
            
        for plan in rate_plans:
            key = (rt.id, plan.id)
            nightly_rates = rates_by_combo.get(key, {})
            if len(nightly_rates) < nights:
                if rt.default_price and rt.default_price > 0:
                    nightly_rates = {d: rt.default_price for d in stay_dates}
                else:
                    continue

            total_price = sum(nightly_rates.values())
            results.append({
                'room_type': rt,
                'rate_plan': plan,
                'available_rooms': free_rooms_count,
                'total_price': total_price,
                'nightly_avg_price': round(total_price / nights, 2),
            })

    return render(request, 'public/search_results.html', {
        'property': property_obj,
        'check_in': check_in_date,
        'check_out': check_out_date,
        'nights': nights,
        'adults': adults,
        'results': results,
    })

def booking_form(request):
    """
    GET: shows the guest details form for the selected room type/rate plan.
    POST: creates the Guest (if new) + Booking via create_booking(),
          then redirects to the confirmation page.

    Note: at this stage we still need to pick an actual physical Room
    (not just RoomType) to pass into create_booking() — we auto-assign
    the first available room of that type for the stay, since the guest
    only cares about room category, not which specific unit.
    """
    property_id = request.GET.get('property') or request.POST.get('property')
    room_type_id = request.GET.get('room_type') or request.POST.get('room_type')
    rate_plan_id = request.GET.get('rate_plan') or request.POST.get('rate_plan')
    check_in = request.GET.get('check_in') or request.POST.get('check_in')
    check_out = request.GET.get('check_out') or request.POST.get('check_out')
    adults = request.GET.get('adults') or request.POST.get('adults', 1)

    if not all([property_id, room_type_id, rate_plan_id, check_in, check_out]):
        messages.error(request, 'Missing booking details. Please search again.')
        return redirect('public:landing')

    property_obj = Property.objects.filter(id=property_id).first()
    room_type = RoomType.objects.filter(id=room_type_id).first()
    rate_plan = RatePlan.objects.filter(id=rate_plan_id).first()

    if not all([property_obj, room_type, rate_plan]):
        messages.error(request, 'Selected room is no longer available.')
        return redirect('public:landing')

    check_in_date = date_cls.fromisoformat(check_in)
    check_out_date = date_cls.fromisoformat(check_out)
    nights = (check_out_date - check_in_date).days

    # Recalculate price for display (same logic as search) so the guest
    # sees an accurate total before submitting.

    stay_dates = [check_in_date + timedelta(days=i) for i in range(nights)]
    rates = list(RoomRate.objects.filter(
        room_type=room_type, rate_plan=rate_plan, date__in=stay_dates
    ).values_list('base_price', flat=True))

    if len(rates) < len(stay_dates):
        # Fall back to RoomType.default_price for any night without
        # a specific RoomRate row — same fallback used in search and
        # booking creation, so the price shown here always matches
        # what create_booking() will actually charge.
        missing_nights = len(stay_dates) - len(rates)
        rates += [room_type.default_price] * missing_nights

    total_price = sum(rates)

    if request.method == 'POST':
        first_name = request.POST.get('first_name', '').strip()
        last_name = request.POST.get('last_name', '').strip()
        email = request.POST.get('email', '').strip()
        phone = request.POST.get('phone', '').strip()
        special_requests = request.POST.get('special_requests', '').strip()

        # if not all([first_name, last_name, email, phone]):
        #     messages.error(request, 'Please fill in all required guest details.')
        #     return render(request, 'public/booking_form.html', {
        #         'property': property_obj, 'room_type': room_type, 'rate_plan': rate_plan,
        #         'check_in': check_in_date, 'check_out': check_out_date, 'nights': nights,
        #         'adults': adults, 'total_price': total_price,
        #     })

        if not all([first_name, last_name, email, phone]):
            messages.error(request, 'Please fill in all required guest details.')
            return render(request, 'public/booking_form.html', {
                'property': property_obj, 'room_type': room_type, 'rate_plan': rate_plan,
                'check_in': check_in_date, 'check_out': check_out_date, 'nights': nights,
                'adults': adults, 'total_price': total_price,
            })

        verified_otp = EmailOTP.objects.filter(
            email=email, is_verified=True
        ).order_by('-created_at').first()
        if not verified_otp:
            messages.error(request, 'Please verify your email with the OTP before confirming.')
            return render(request, 'public/booking_form.html', {
                'property': property_obj, 'room_type': room_type, 'rate_plan': rate_plan,
                'check_in': check_in_date, 'check_out': check_out_date, 'nights': nights,
                'adults': adults, 'total_price': total_price,
            })

        # Find or create the guest by email
        guest, _ = Guest.objects.get_or_create(
            email=email,
            defaults={'first_name': first_name, 'last_name': last_name, 'phone': phone}
        )

        # Auto-assign the first physically free room of this type for the whole stay
        blocked_room_ids = set(
            Availability.objects.filter(date__in=stay_dates)
            .filter(Q(is_available=False) | Q(is_blocked=True))
            .values_list('room_id', flat=True).distinct()
        )
        available_room = Room.objects.filter(
            room_type=room_type, is_active=True
        ).exclude(id__in=blocked_room_ids).first()

        if not available_room:
            messages.error(request, 'Sorry, this room was just booked by someone else. Please search again.')
            return redirect('public:landing')

        try:
            booking = create_booking(
                property_obj=property_obj,
                guest=guest,
                check_in_date=check_in_date,
                check_out_date=check_out_date,
                room_requests=[{
                    'room_id': available_room.id,
                    'room_type_id': room_type.id,
                    'rate_plan_id': rate_plan.id,
                    'adults': int(adults),
                }],
                source='WEBSITE',
                adults=int(adults),
                special_requests=special_requests,
            )
        except RoomNotAvailableError:
            messages.error(request, 'Sorry, this room was just booked by someone else. Please search again.')
            return redirect('public:landing')
        except ValidationError as e:
            messages.error(request, str(e))
            return redirect('public:landing')

        return redirect('public:confirmation', booking_number=booking.booking_number)

    return render(request, 'public/booking_form.html', {
        'property': property_obj, 'room_type': room_type, 'rate_plan': rate_plan,
        'check_in': check_in_date, 'check_out': check_out_date, 'nights': nights,
        'adults': adults, 'total_price': total_price,
    })


def confirmation(request, booking_number):
    from apps.bookings.models import Booking
    booking = Booking.objects.select_related('guest', 'property').prefetch_related(
        'booking_rooms__room', 'booking_rooms__room_type'
    ).filter(booking_number=booking_number).first()

    if not booking:
        messages.error(request, 'Booking not found.')
        return redirect('public:landing')

    return render(request, 'public/confirmation.html', {'booking': booking})

def view_invoice(request, booking_number):
    from django.shortcuts import get_object_or_404
    from apps.bookings.models import Booking, Invoice
    from apps.bookings.services import generate_invoice

    booking = get_object_or_404(Booking, booking_number=booking_number)

    invoice = Invoice.objects.filter(booking=booking).first()
    if not invoice:
        invoice = generate_invoice(booking.id)

    return render(request, 'public/invoice.html', {
        'booking': booking,
        'invoice': invoice,
    })

@csrf_exempt
@require_POST
def send_booking_otp(request):
    """
    POST /book/otp/send/  Body: {"email": "guest@example.com"}
    Generates a 6-digit OTP, emails it, and returns success. Frontend
    calls this when the guest fills in their email on the booking form.
    """
    try:
        data = json.loads(request.body)
        email = data.get('email', '').strip()
    except (json.JSONDecodeError, AttributeError):
        return JsonResponse({'success': False, 'message': 'Invalid request.'}, status=400)

    if not email or '@' not in email:
        return JsonResponse({'success': False, 'message': 'Please enter a valid email.'}, status=400)

    otp = EmailOTP.generate_for(email)

    send_mail(
        subject='Your booking verification code',
        message=f'Your verification code is: {otp.code}\n\nThis code expires in 10 minutes.',
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[email],
        fail_silently=False,
    )

    return JsonResponse({'success': True, 'message': f'Verification code sent to {email}.'})


@csrf_exempt
@require_POST
def verify_booking_otp(request):
    """
    POST /book/otp/verify/  Body: {"email": "...", "code": "123456"}
    Marks the most recent valid OTP for this email as verified.
    """
    try:
        data = json.loads(request.body)
        email = data.get('email', '').strip()
        code = data.get('code', '').strip()
    except (json.JSONDecodeError, AttributeError):
        return JsonResponse({'success': False, 'message': 'Invalid request.'}, status=400)

    otp = EmailOTP.objects.filter(email=email, code=code).order_by('-created_at').first()

    if not otp or not otp.is_valid():
        return JsonResponse({'success': False, 'message': 'Invalid or expired code.'}, status=400)

    otp.is_verified = True
    otp.save(update_fields=['is_verified', 'updated_at'])

    return JsonResponse({'success': True, 'message': 'Email verified successfully.'})