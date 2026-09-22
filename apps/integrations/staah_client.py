import requests
from django.conf import settings
from django.utils import timezone
from django.db.models import Count as models_count
from apps.availability.models import Availability, RoomRate, Restriction
from .models import ChannelMapping, SyncLog


class STAAHNotConfiguredError(Exception):
    """Raised when STAAH credentials aren't set — lets callers fail
    gracefully/log clearly instead of crashing with a confusing HTTP error."""
    pass


def _get_headers():
    if not settings.STAAH_API_KEY or not settings.STAAH_API_SECRET:
        raise STAAHNotConfiguredError(
            "STAAH_API_KEY / STAAH_API_SECRET are not set in .env. "
            "Sync will not run until credentials are configured."
        )
    return {
        'Authorization': f'Bearer {settings.STAAH_API_KEY}',
        'Content-Type': 'application/json',
    }


def _log_sync(*, property_obj, sync_type, direction, status, request_payload=None,
              response_payload=None, error_message=''):
    return SyncLog.objects.create(
        property=property_obj,
        sync_type=sync_type,
        direction=direction,
        status=status,
        request_payload=request_payload,
        response_payload=response_payload,
        error_message=error_message,
    )


def push_availability(property_obj, start_date, end_date):
    """
    Pushes room-level availability counts to STAAH for a date range.
    STAAH expects availability per ROOM TYPE (not per physical room),
    so we aggregate: count of rooms with is_available=True per
    (room_type, date), using the ChannelMapping to translate our
    room_type IDs to STAAH's room IDs.
    """
    mappings = ChannelMapping.objects.filter(property=property_obj, room_type__isnull=False)
    if not mappings.exists():
        _log_sync(
            property_obj=property_obj, sync_type=SyncLog.SyncType.AVAILABILITY,
            direction=SyncLog.Direction.OUTBOUND, status=SyncLog.Status.FAILED,
            error_message="No ChannelMapping configured for this property's room types."
        )
        return

    payload_items = []
    for mapping in mappings:
        counts_by_date = (
            Availability.objects.filter(
                room__room_type=mapping.room_type,
                date__range=(start_date, end_date),
                is_available=True,
                is_blocked=False,
            )
            .values('date')
            .annotate(available_count=models_count('room'))
        )
        for row in counts_by_date:
            payload_items.append({
                'staah_property_id': mapping.staah_property_id,
                'staah_room_id': mapping.staah_room_id,
                'date': row['date'].isoformat(),
                'available': row['available_count'],
            })

    payload = {'property_id': mappings.first().staah_property_id, 'availability': payload_items}

    try:
        headers = _get_headers()
        response = requests.post(
            f"{settings.STAAH_API_BASE_URL}/v1/availability", json=payload, headers=headers, timeout=15
        )
        response.raise_for_status()
        _log_sync(
            property_obj=property_obj, sync_type=SyncLog.SyncType.AVAILABILITY,
            direction=SyncLog.Direction.OUTBOUND, status=SyncLog.Status.SUCCESS,
            request_payload=payload, response_payload=response.json(),
        )
        return response.json()
    except STAAHNotConfiguredError as e:
        _log_sync(
            property_obj=property_obj, sync_type=SyncLog.SyncType.AVAILABILITY,
            direction=SyncLog.Direction.OUTBOUND, status=SyncLog.Status.FAILED,
            request_payload=payload, error_message=str(e),
        )
    except requests.RequestException as e:
        _log_sync(
            property_obj=property_obj, sync_type=SyncLog.SyncType.AVAILABILITY,
            direction=SyncLog.Direction.OUTBOUND, status=SyncLog.Status.FAILED,
            request_payload=payload, error_message=str(e),
        )


def push_rates(property_obj, start_date, end_date):
    """Pushes RoomRate rows to STAAH, same mapping/logging pattern as availability."""
    mappings = ChannelMapping.objects.filter(
        property=property_obj, room_type__isnull=False, rate_plan__isnull=False
    )
    if not mappings.exists():
        _log_sync(
            property_obj=property_obj, sync_type=SyncLog.SyncType.RATE,
            direction=SyncLog.Direction.OUTBOUND, status=SyncLog.Status.FAILED,
            error_message="No ChannelMapping configured for room_type + rate_plan combos."
        )
        return

    payload_items = []
    for mapping in mappings:
        rates = RoomRate.objects.filter(
            room_type=mapping.room_type, rate_plan=mapping.rate_plan,
            date__range=(start_date, end_date),
        )
        for rate in rates:
            payload_items.append({
                'staah_room_id': mapping.staah_room_id,
                'staah_rate_plan_id': mapping.staah_rate_plan_id,
                'date': rate.date.isoformat(),
                'price': str(rate.base_price),
            })

    payload = {'property_id': mappings.first().staah_property_id, 'rates': payload_items}

    try:
        headers = _get_headers()
        response = requests.post(
            f"{settings.STAAH_API_BASE_URL}/v1/rates", json=payload, headers=headers, timeout=15
        )
        response.raise_for_status()
        _log_sync(
            property_obj=property_obj, sync_type=SyncLog.SyncType.RATE,
            direction=SyncLog.Direction.OUTBOUND, status=SyncLog.Status.SUCCESS,
            request_payload=payload, response_payload=response.json(),
        )
        return response.json()
    except STAAHNotConfiguredError as e:
        _log_sync(
            property_obj=property_obj, sync_type=SyncLog.SyncType.RATE,
            direction=SyncLog.Direction.OUTBOUND, status=SyncLog.Status.FAILED,
            request_payload=payload, error_message=str(e),
        )
    except requests.RequestException as e:
        _log_sync(
            property_obj=property_obj, sync_type=SyncLog.SyncType.RATE,
            direction=SyncLog.Direction.OUTBOUND, status=SyncLog.Status.FAILED,
            request_payload=payload, error_message=str(e),
        )

def _json_safe_payload(payload):
    """Converts date/datetime objects to ISO strings so the payload
    can be stored in a JSONField for sync logging."""
    import datetime
    safe = {}
    for k, v in payload.items():
        if isinstance(v, (datetime.date, datetime.datetime)):
            safe[k] = v.isoformat()
        else:
            safe[k] = v
    return safe

def handle_incoming_reservation(property_obj, staah_payload):
    """
    Called from the webhook receiver when STAAH notifies us of a new
    OTA reservation. Translates STAAH's room/rate IDs back to ours via
    ChannelMapping, then calls the SAME create_booking() used by the
    website/API — meaning OTA reservations get identical atomic
    double-booking protection as any other booking source.
    """
    from apps.bookings.services import create_booking, RoomNotAvailableError
    from apps.guests.models import Guest
    from apps.properties.models import Room

    try:
        staah_room_id = staah_payload['room_id']
        staah_rate_plan_id = staah_payload['rate_plan_id']
        mapping = ChannelMapping.objects.get(
            property=property_obj, staah_room_id=staah_room_id, staah_rate_plan_id=staah_rate_plan_id
        )

        guest, _ = Guest.objects.get_or_create(
            email=staah_payload['guest_email'],
            defaults={
                'first_name': staah_payload.get('guest_first_name', ''),
                'last_name': staah_payload.get('guest_last_name', ''),
                'phone': staah_payload.get('guest_phone', ''),
            }
        )

        # Auto-assign first available physical room of the mapped room_type
        available_room = Room.objects.filter(room_type=mapping.room_type, is_active=True).first()
        if not available_room:
            raise RoomNotAvailableError("No physical room available for the mapped room type.")

        from apps.bookings.models import Booking
        booking = create_booking(
            property_obj=property_obj,
            guest=guest,
            check_in_date=staah_payload['check_in'],
            check_out_date=staah_payload['check_out'],
            room_requests=[{
                'room_id': available_room.id,
                'room_type_id': mapping.room_type_id,
                'rate_plan_id': mapping.rate_plan_id,
                'adults': staah_payload.get('adults', 1),
            }],
            source=Booking.Source.OTHER_OTA,  # refine to BOOKING_COM/AGODA/EXPEDIA using payload's channel field
        )
        booking.ota_reference = staah_payload.get('ota_reservation_id', '')
        booking.save(update_fields=['ota_reference'])

        _log_sync(
            property_obj=property_obj, sync_type=SyncLog.SyncType.RESERVATION_IN,
            direction=SyncLog.Direction.INBOUND, status=SyncLog.Status.SUCCESS,
            request_payload=_json_safe_payload(staah_payload), response_payload={'booking_number': booking.booking_number},
        )
        return booking

    except Exception as e:
        _log_sync(
            property_obj=property_obj, sync_type=SyncLog.SyncType.RESERVATION_IN,
            direction=SyncLog.Direction.INBOUND, status=SyncLog.Status.FAILED,
            request_payload=_json_safe_payload(staah_payload), error_message=str(e),
        )
        raise
    