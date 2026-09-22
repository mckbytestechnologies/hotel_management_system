import uuid
from datetime import timedelta

from django.db import transaction
from django.core.exceptions import ValidationError

from apps.availability.models import Availability
from apps.availability.models import RoomRate
from apps.properties.models import RoomType
from .models import Booking, BookingRoom
from django.utils import timezone
from apps.properties.models import Room
import uuid as uuid_lib
from django.utils import timezone
from .models import Payment, Invoice, Refund
from django.core.mail import send_mail
from django.conf import settings as django_settings


class RoomNotAvailableError(Exception):
    """Raised when one or more requested rooms are no longer bookable
    for the requested dates — caught by the view to return a 409/400."""
    pass


def generate_booking_number():
    return f"BK{uuid.uuid4().hex[:10].upper()}"


@transaction.atomic
def create_booking(*, property_obj, guest, check_in_date, check_out_date,
                    room_requests, source='DIRECT', adults=1, children=0,
                    special_requests=''):
    """
    Creates a Booking + BookingRoom rows and atomically reserves the
    requested rooms' Availability records.

    room_requests: list of dicts, each like:
        {'room_id': 5, 'room_type_id': 1, 'rate_plan_id': 1, 'adults': 2, 'children': 0}

    THE CONCURRENCY-SAFE PART:
    We use select_for_update() to lock the exact Availability rows this
    booking needs BEFORE checking if they're free. Any other request
    trying to book the same room+date will be forced to wait at the
    database level until this transaction commits (frees the lock) or
    rolls back. This is what makes it impossible for two simultaneous
    requests to both "see" a room as free and both book it.
    """
    nights = (check_out_date - check_in_date).days
    if nights <= 0:
        raise ValidationError("check_out_date must be after check_in_date.")

    stay_dates = [check_in_date + timedelta(days=i) for i in range(nights)]
    room_ids = [r['room_id'] for r in room_requests]

    # --- STEP 1: Lock the relevant Availability rows ---
    # order_by('id') keeps lock acquisition order consistent across
    # concurrent transactions, which avoids deadlocks when two bookings
    # request overlapping sets of rooms in different orders.
        # --- STEP 0: Ensure an Availability row exists for every room/date
    # this booking needs. Rooms are considered available-by-default
    # (matching Availability.is_available's default) unless explicitly
    # blocked — so a missing row should mean "never touched, therefore
    # open," not "unavailable." This also keeps search/pricing fallback
    # (RoomType.default_price) consistent with what booking actually allows.
    for room_id in room_ids:
        for d in stay_dates:
            Availability.objects.get_or_create(
                room_id=room_id, date=d,
                defaults={'property_id': property_obj.id, 'is_available': True, 'is_blocked': False}
            )

    # --- STEP 1: Lock the relevant Availability rows ---
    # order_by('id') keeps lock acquisition order consistent across
    # concurrent transactions, which avoids deadlocks when two bookings
    # request overlapping sets of rooms in different orders.
    locked_availabilities = list(
        Availability.objects.select_for_update()
        .filter(room_id__in=room_ids, date__in=stay_dates)
        .order_by('id')
    )

    # Index them for fast lookup: (room_id, date) -> Availability row
    availability_map = {(a.room_id, a.date): a for a in locked_availabilities}

    # --- STEP 2: Re-check availability NOW, under the lock ---
    unavailable = []
    for room_id in room_ids:
        for d in stay_dates:
            row = availability_map.get((room_id, d))
            if row is None:
                # No Availability row exists for this room/date at all —
                # treat as unavailable rather than silently allowing it,
                # since every sellable date should have an explicit row.
                unavailable.append((room_id, d))
            elif not row.is_available or row.is_blocked:
                unavailable.append((room_id, d))

    if unavailable:
        raise RoomNotAvailableError(
            f"The following room/date combinations are no longer available: {unavailable}"
        )

    # --- STEP 3: All clear — create the Booking header ---
    booking = Booking.objects.create(
        booking_number=generate_booking_number(),
        property=property_obj,
        guest=guest,
        check_in_date=check_in_date,
        check_out_date=check_out_date,
        status=Booking.Status.CONFIRMED,
        source=source,
        adults=adults,
        children=children,
        special_requests=special_requests,
    )

    total_amount = 0
    booking_rooms = []

    for req in room_requests:
        # Sum the actual nightly rates for this room's room_type+rate_plan
        # across the stay — this is the real price, not a flat estimate.
        rates = list(RoomRate.objects.filter(
            room_type_id=req['room_type_id'],
            rate_plan_id=req['rate_plan_id'],
            date__in=stay_dates,
        ).values_list('base_price', flat=True))

        if len(rates) < len(stay_dates):
            # Fill missing nights using the RoomType's fixed default price,
            # so pricing works even when no date-specific RoomRate rows
            # have been generated for this stay range yet.
            room_type = RoomType.objects.get(id=req['room_type_id'])
            missing_nights = len(stay_dates) - len(rates)
            rates += [room_type.default_price] * missing_nights

        rate_amount = sum(rates)
        total_amount += rate_amount

        booking_room = BookingRoom.objects.create(
            booking=booking,
            room_id=req['room_id'],
            room_type_id=req['room_type_id'],
            rate_plan_id=req['rate_plan_id'],
            check_in_date=check_in_date,
            check_out_date=check_out_date,
            rate_amount=rate_amount,
            adults=req.get('adults', 1),
            children=req.get('children', 0),
        )
        booking_rooms.append(booking_room)

        # --- STEP 4: Mark the locked Availability rows as booked ---
        for d in stay_dates:
            row = availability_map.get((req['room_id'], d))
            if row is not None:
                row.is_available = False
                row.booking_room = booking_room
                row.save(update_fields=['is_available', 'booking_room', 'updated_at'])

    booking.total_amount = total_amount
    booking.save(update_fields=['total_amount', 'updated_at'])

    return booking



class InvalidBookingStateError(Exception):
    """Raised when a check-in/check-out is attempted from an invalid status."""
    pass


@transaction.atomic
def check_in_booking(booking_id):
    """
    Transitions a Booking from CONFIRMED -> CHECKED_IN and flips all its
    rooms to OCCUPIED in ONE bulk update query (not a loop of .save()
    calls per room — critical for bookings with many rooms).

    select_for_update() on the Booking row itself prevents two concurrent
    requests (e.g. two front-desk clicks) from both processing the same
    check-in simultaneously.
    """
    booking = Booking.objects.select_for_update().select_related('property').get(id=booking_id)

    if booking.status != Booking.Status.CONFIRMED:
        raise InvalidBookingStateError(
            f"Cannot check in a booking with status '{booking.status}'. Must be CONFIRMED."
        )

    room_ids = list(booking.booking_rooms.values_list('room_id', flat=True))

    # Single bulk UPDATE statement — O(1) query regardless of room count.
    Room.objects.filter(id__in=room_ids).update(
        status=Room.RoomStatus.OCCUPIED, updated_at=timezone.now()
    )

    booking.status = Booking.Status.CHECKED_IN
    booking.save(update_fields=['status', 'updated_at'])

    return booking


@transaction.atomic
def check_out_booking(booking_id):
    """
    Transitions CHECKED_IN -> CHECKED_OUT, releases rooms back to
    AVAILABLE in one bulk update, same locking/performance pattern
    as check_in_booking().
    """
    booking = Booking.objects.select_for_update().select_related('property').get(id=booking_id)

    if booking.status != Booking.Status.CHECKED_IN:
        raise InvalidBookingStateError(
            f"Cannot check out a booking with status '{booking.status}'. Must be CHECKED_IN."
        )

    room_ids = list(booking.booking_rooms.values_list('room_id', flat=True))

    Room.objects.filter(id__in=room_ids).update(
        status=Room.RoomStatus.AVAILABLE, updated_at=timezone.now()
    )

    booking.status = Booking.Status.CHECKED_OUT
    booking.save(update_fields=['status', 'updated_at'])

    return booking


class PaymentError(Exception):
    """Raised for invalid payment operations (e.g. overpayment beyond
    what makes sense, refunding more than was paid)."""
    pass


def generate_invoice_number():
    return f"INV{uuid_lib.uuid4().hex[:10].upper()}"


@transaction.atomic
def record_payment(*, booking_id, amount, method, transaction_reference='',
                    notes='', received_by=None, status=Payment.Status.SUCCESS):
    """
    Records a payment against a booking and updates Booking.paid_amount
    atomically. select_for_update() on the booking prevents a race where
    two simultaneous payment recordings both read a stale paid_amount
    and overwrite each other's update.
    """
    booking = Booking.objects.select_for_update().get(id=booking_id)

    payment = Payment.objects.create(
        booking=booking,
        amount=amount,
        method=method,
        status=status,
        transaction_reference=transaction_reference,
        notes=notes,
        received_by=received_by,
        paid_at=timezone.now() if status == Payment.Status.SUCCESS else None,
    )

    if status == Payment.Status.SUCCESS:
        booking.paid_amount = booking.paid_amount + amount
        booking.save(update_fields=['paid_amount', 'updated_at'])

    return payment


@transaction.atomic
def generate_invoice(booking_id):
    """
    Builds (or regenerates) an Invoice snapshot from the booking's
    current BookingRoom charges. Regenerating overwrites the existing
    invoice's line items/totals rather than creating duplicates, since
    a booking should have exactly one current invoice.
    """
    booking = Booking.objects.select_related('property', 'guest').prefetch_related(
        'booking_rooms__room_type'
    ).get(id=booking_id)

    line_items = []
    subtotal = 0
    for br in booking.booking_rooms.all():
        line_items.append({
            'description': f"{br.room_type.name} ({br.check_in_date} to {br.check_out_date})",
            'amount': str(br.rate_amount),
        })
        subtotal += br.rate_amount

    # Flat placeholder tax/discount logic — replace with real tax rules
    # (GST slabs, property-level tax config) when that requirement is defined.
    tax_amount = 0
    discount_amount = 0
    total_amount = subtotal + tax_amount - discount_amount

    invoice, _ = Invoice.objects.update_or_create(
        booking=booking,
        defaults={
            'invoice_number': generate_invoice_number(),
            'line_items': line_items,
            'subtotal': subtotal,
            'tax_amount': tax_amount,
            'discount_amount': discount_amount,
            'total_amount': total_amount,
        }
    )
    return invoice


@transaction.atomic
def process_refund(*, payment_id, amount, reason='', processed_by=None):
    """
    Processes a refund against a specific Payment. Validates the refund
    doesn't exceed what's actually refundable (payment amount minus
    any already-refunded amount), and updates the Payment's status
    and the Booking's paid_amount atomically.
    """
    payment = Payment.objects.select_for_update().select_related('booking').get(id=payment_id)

    if payment.status not in (Payment.Status.SUCCESS, Payment.Status.PARTIALLY_REFUNDED):
        raise PaymentError(f"Cannot refund a payment with status '{payment.status}'.")

    already_refunded = payment.refunds.filter(
        status=Refund.Status.PROCESSED
    ).aggregate(total=models.Sum('amount'))['total'] or 0

    refundable = payment.amount - already_refunded
    if amount > refundable:
        raise PaymentError(
            f"Refund amount ({amount}) exceeds refundable balance ({refundable})."
        )

    refund = Refund.objects.create(
        payment=payment,
        booking=payment.booking,
        amount=amount,
        reason=reason,
        status=Refund.Status.PROCESSED,
        processed_at=timezone.now(),
        processed_by=processed_by,
    )

    new_total_refunded = already_refunded + amount
    payment.status = (
        Payment.Status.REFUNDED if new_total_refunded >= payment.amount
        else Payment.Status.PARTIALLY_REFUNDED
    )
    payment.save(update_fields=['status', 'updated_at'])

    booking = payment.booking
    booking.paid_amount = booking.paid_amount - amount
    booking.save(update_fields=['paid_amount', 'updated_at'])

    return refund

from django.core.mail import send_mail
from django.conf import settings as django_settings


def send_booking_confirmation_email(booking):
    """
    Sends the guest their booking details by email. Called after
    successful payment verification (Razorpay verify_payment / webhook),
    so the guest has a permanent record beyond the confirmation page.
    """
    room_lines = "\n".join(
        f"- {br.room_type.name} (Room {br.room.room_number}): {br.check_in_date} to {br.check_out_date} — ₹{br.rate_amount}"
        for br in booking.booking_rooms.all()
    )

    message = f"""Dear {booking.guest.full_name},

Your booking at {booking.property.name} is confirmed!

Booking Number: {booking.booking_number}
Check-in: {booking.check_in_date}
Check-out: {booking.check_out_date}

Rooms:
{room_lines}

Total Amount: ₹{booking.total_amount}
Paid Amount: ₹{booking.paid_amount}

Thank you for choosing {booking.property.name}. We look forward to hosting you!
"""

    send_mail(
        subject=f'Booking Confirmed - {booking.booking_number}',
        message=message,
        from_email=django_settings.DEFAULT_FROM_EMAIL,
        recipient_list=[booking.guest.email],
        fail_silently=False,
    )

def send_admin_booking_notification(booking):
    """
    Notifies the property/admin email whenever a booking is confirmed,
    so front desk sees new reservations without needing to check the
    dashboard constantly. Separate function from the guest email since
    the two have different audiences and could diverge in content later
    (e.g. admin version could include guest phone/notes, internal flags).
    """
    if not django_settings.ADMIN_NOTIFICATION_EMAIL:
        return  # not configured — skip silently rather than erroring

    room_lines = "\n".join(
        f"- {br.room_type.name} (Room {br.room.room_number}): {br.check_in_date} to {br.check_out_date} — ₹{br.rate_amount}"
        for br in booking.booking_rooms.all()
    )

    message = f"""New booking received.

Booking Number: {booking.booking_number}
Property: {booking.property.name}
Source: {booking.get_source_display()}
Guest: {booking.guest.full_name}
Guest Email: {booking.guest.email}
Guest Phone: {booking.guest.phone}

Check-in: {booking.check_in_date}
Check-out: {booking.check_out_date}

Rooms:
{room_lines}

Total Amount: ₹{booking.total_amount}
Paid Amount: ₹{booking.paid_amount}
Balance Due: ₹{booking.balance_due()}

Special Requests: {booking.special_requests or 'None'}
"""

    send_mail(
        subject=f'New Booking - {booking.booking_number}',
        message=message,
        from_email=django_settings.DEFAULT_FROM_EMAIL,
        recipient_list=[django_settings.ADMIN_NOTIFICATION_EMAIL],
        fail_silently=False,
    )