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
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.utils.html import strip_tags
from urllib.parse import quote_plus
from urllib.parse import urlencode
from django.core.paginator import Paginator
from django.db.models import Count, Exists, Min, OuterRef, Q
from django.urls import reverse


PLACEHOLDER_IMAGE = 'https://images.unsplash.com/photo-1566073771259-6a8506099945?auto=format&fit=crop&w=1200&q=80'

def build_property_cards(properties):
    """
    Turns each active property into a plain dict for the landing page
    cards and popup. Everything is serialised here so the template can
    hand it to the browser as JSON (json_script) with no extra queries.
    """
    cards = []
    for p in properties:
        images = [
            {'url': img.image.url, 'caption': img.caption}
            for img in p.images.all() if img.is_active
        ] or [{'url': PLACEHOLDER_IMAGE, 'caption': ''}]

        room_types = [rt for rt in p.room_types.all() if rt.is_active]
        prices = [float(rt.default_price) for rt in room_types
                  if rt.default_price and rt.default_price > 0]

        full_address = ', '.join(x for x in [p.address, p.city, p.state, p.country] if x)
        query = quote_plus(full_address)

        cards.append({
            'id': p.id,
            'name': p.name,
            'city': p.city,
            'address': full_address,
            'phone': p.phone,
            'check_in_time': p.check_in_time.strftime('%I:%M %p').lstrip('0'),
            'check_out_time': p.check_out_time.strftime('%I:%M %p').lstrip('0'),
            'images': images,
            'room_types': [
                {
                    'name': rt.name,
                    'max_occupancy': rt.max_occupancy,
                    'price': float(rt.default_price) if rt.default_price and rt.default_price > 0 else None,
                }
                for rt in room_types
            ],
            'starting_price': min(prices) if prices else None,
            'map_embed_url': f'https://www.google.com/maps?q={query}&output=embed',
            'map_link': f'https://www.google.com/maps/search/?api=1&query={query}',
        })
    return cards

def landing_page(request):
    """
    The public homepage: a hero search form (property, check-in, check-out,
    guests). Submitting redirects to the search results page with these
    as query params — keeps the results page bookmarkable/shareable.
    """
    properties = Property.objects.filter(is_active=True).prefetch_related('images', 'room_types')

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
        'property_cards': build_property_cards(properties),

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
        'property_images': property_obj.images.filter(is_active=True)[:5],
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
    Generates a 6-digit OTP, emails it as a styled HTML message (with
    plain-text fallback), and returns success. Frontend calls this when
    the guest fills in their email on the booking form.
    """
    try:
        data = json.loads(request.body)
        email = data.get('email', '').strip()
    except (json.JSONDecodeError, AttributeError):
        return JsonResponse({'success': False, 'message': 'Invalid request.'}, status=400)

    if not email or '@' not in email:
        return JsonResponse({'success': False, 'message': 'Please enter a valid email.'}, status=400)

    if not EmailOTP.can_request_new(email):
        wait_seconds = EmailOTP.seconds_until_next_request(email)
        return JsonResponse({
            'success': False,
            'message': f'Please wait {wait_seconds} seconds before requesting another code.'
        }, status=429)

    otp = EmailOTP.generate_for(email)

    html_content = render_to_string('public/Bookingsemails/otp_code.html', {
        'code': otp.code,
        'property_name': 'M Square',
    })
    text_content = strip_tags(html_content)

    email_msg = EmailMultiAlternatives(
        subject='Your booking verification code',
        body=text_content,
        from_email=settings.DEFAULT_FROM_EMAIL,
        to=[email],
    )
    email_msg.attach_alternative(html_content, "text/html")
    email_msg.send(fail_silently=False)

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

PRICE_BANDS = {
    'lt1000':    ('Under ₹1,000', 0, 1000),
    '1000-2500': ('₹1,000 – ₹2,500', 1000, 2500),
    '2500-5000': ('₹2,500 – ₹5,000', 2500, 5000),
    'gt5000':    ('₹5,000 and above', 5000, None),
}
SORT_OPTIONS = [
    ('recommended', 'Recommended'),
    ('price_asc', 'Price (low to high)'),
    ('price_desc', 'Price (high to low)'),
    ('rooms', 'Most rooms left'),
]
STAYS_PAGE_SIZE = 8


def _parse_date(value, fallback):
    try:
        return date_cls.fromisoformat(value)
    except (TypeError, ValueError):
        return fallback


def _querystring(request, drop=(), remove_value=None):
    """Current query string with some params removed, so sort links and
    filter chips keep everything else the guest has selected."""
    params = request.GET.copy()
    if remove_value:
        key, val = remove_value
        params.setlist(key, [v for v in params.getlist(key) if v != val])
    for k in drop:
        params.pop(k, None)
    return params.urlencode()


def stays(request):
    """
    Public listing of all active properties with filters, sorting and
    per-date availability. Filtering happens in the database; the
    availability-dependent sort and the pagination happen on the (small)
    filtered list, which is fine for tens to a few hundred properties.
    """
    today = date_cls.today()
    check_in = max(_parse_date(request.GET.get('check_in'), today + timedelta(days=1)), today)
    check_out = _parse_date(request.GET.get('check_out'), check_in + timedelta(days=1))
    if check_out <= check_in:
        check_out = check_in + timedelta(days=1)
    if check_out > check_in + timedelta(days=90):
        check_out = check_in + timedelta(days=90)   # keeps the date list bounded
    nights = (check_out - check_in).days
    stay_dates = [check_in + timedelta(days=i) for i in range(nights)]

    try:
        adults = max(1, min(int(request.GET.get('adults', 2)), 12))
    except ValueError:
        adults = 2

    q = request.GET.get('q', '').strip()
    city = request.GET.get('city', '').strip()
    bands = [b for b in request.GET.getlist('price') if b in PRICE_BANDS]
    free_cancel = request.GET.get('free_cancel') == '1'
    breakfast = request.GET.get('breakfast') == '1'
    sort = request.GET.get('sort', 'recommended')
    if sort not in dict(SORT_OPTIONS):
        sort = 'recommended'

    qs = (
        Property.objects.filter(is_active=True)
        .annotate(min_price=Min(
            'room_types__default_price',
            filter=Q(room_types__is_active=True, room_types__default_price__gt=0),
        ))
        .prefetch_related('images', 'room_types', 'rate_plans')
    )
    if q:
        qs = qs.filter(
            Q(name__icontains=q) | Q(city__icontains=q) |
            Q(address__icontains=q) | Q(state__icontains=q)
        )
    if city:
        qs = qs.filter(city__iexact=city)
    if bands:
        cond = Q()
        for key in bands:
            _, low, high = PRICE_BANDS[key]
            part = Q(min_price__gte=low)
            if high is not None:
                part &= Q(min_price__lt=high)
            cond |= part
        qs = qs.filter(cond)
    if free_cancel:
        qs = qs.filter(Exists(RatePlan.objects.filter(
            property=OuterRef('pk'), is_active=True, is_refundable=True)))
    if breakfast:
        qs = qs.filter(Exists(RatePlan.objects.filter(
            property=OuterRef('pk'), is_active=True).exclude(meal_plan='')))
    if adults > 1:
        qs = qs.filter(Exists(RoomType.objects.filter(
            property=OuterRef('pk'), is_active=True, max_occupancy__gte=adults)))

    props = list(qs)

    # Rooms left per property for the chosen dates: two queries in total.
    blocked_room_ids = set(
        Availability.objects.filter(date__in=stay_dates)
        .filter(Q(is_available=False) | Q(is_blocked=True))
        .values_list('room_id', flat=True).distinct()
    )
    rooms_left = {}
    room_rows = Room.objects.filter(
        is_active=True, property_id__in=[p.id for p in props],
        room_type__is_active=True, room_type__max_occupancy__gte=adults,
    ).values_list('property_id', 'id')
    for pid, rid in room_rows:
        if rid not in blocked_room_ids:
            rooms_left[pid] = rooms_left.get(pid, 0) + 1

    def sort_key(p):
        no_price = p.min_price is None
        if sort == 'price_asc':
            key = (no_price, p.min_price or 0)
        elif sort == 'price_desc':
            key = (no_price, -(p.min_price or 0))
        elif sort == 'rooms':
            key = (-rooms_left.get(p.id, 0), p.name.lower())
        else:
            key = (0, p.name.lower())
        return (rooms_left.get(p.id, 0) == 0, key)   # sold-out always last

    props.sort(key=sort_key)

    paginator = Paginator(props, STAYS_PAGE_SIZE)
    page_obj = paginator.get_page(request.GET.get('page'))

    cards = build_property_cards(page_obj.object_list)
    date_params = {'check_in': check_in.isoformat(), 'check_out': check_out.isoformat(), 'adults': adults}
    for card, p in zip(cards, page_obj.object_list):
        plans = [rp for rp in p.rate_plans.all() if rp.is_active]
        types = [rt for rt in p.room_types.all() if rt.is_active]
        left = rooms_left.get(p.id, 0)
        card.update({
            'rooms_left': left,
            'sold_out': left == 0,
            'free_cancellation': any(rp.is_refundable for rp in plans),
            'breakfast': any(rp.meal_plan for rp in plans),
            'max_guests': max((rt.max_occupancy for rt in types), default=None),
            'book_url': f"{reverse('public:search')}?{urlencode({'property': p.id, **date_params})}",
        })

    chips = []
    if q:
        chips.append((f'"{q}"', _querystring(request, drop=('q', 'page'))))
    if city:
        chips.append((city, _querystring(request, drop=('city', 'page'))))
    for b in bands:
        chips.append((PRICE_BANDS[b][0], _querystring(request, drop=('page',), remove_value=('price', b))))
    if free_cancel:
        chips.append(('Free cancellation', _querystring(request, drop=('free_cancel', 'page'))))
    if breakfast:
        chips.append(('Breakfast included', _querystring(request, drop=('breakfast', 'page'))))

    return render(request, 'public/stays.html', {
        'cards': cards,
        'page_obj': page_obj,
        'total': paginator.count,
        'check_in': check_in, 'check_out': check_out, 'nights': nights, 'adults': adults,
        'q': q, 'city': city, 'bands_selected': bands,
        'free_cancel': free_cancel, 'breakfast': breakfast,
        'sort': sort, 'sort_options': SORT_OPTIONS,
        'price_bands': [(k, v[0]) for k, v in PRICE_BANDS.items()],
        'cities': Property.objects.filter(is_active=True).values('city').annotate(n=Count('id')).order_by('city'),
        'chips': chips,
        'clear_qs': urlencode(date_params),
        'base_qs': _querystring(request, drop=('sort', 'page')),
        'page_qs': _querystring(request, drop=('page',)),
        'min_checkin': today.isoformat(),
    })