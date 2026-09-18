import uuid
from datetime import timedelta

from django.db import transaction
from django.core.exceptions import ValidationError

from apps.availability.models import Availability
from apps.availability.models import RoomRate
from apps.properties.models import RoomType
from .models import Booking, BookingRoom


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