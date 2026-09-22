import requests

from django.conf import settings
from django.db.models import Count

from apps.availability.models import Availability, RoomRate, Restriction
from .models import ChannelMapping, SyncLog


class ChannexNotConfiguredError(Exception):
    pass


def _get_headers():
    if not settings.CHANNEX_API_KEY:
        raise ChannexNotConfiguredError(
            "CHANNEX_API_KEY is not set in .env."
        )

    return {
        "user-api-key": settings.CHANNEX_API_KEY,
        "Content-Type": "application/json",
    }


def _log_sync(
    *,
    property_obj,
    sync_type,
    direction,
    status,
    request_payload=None,
    response_payload=None,
    error_message="",
):
    return SyncLog.objects.create(
        property=property_obj,
        sync_type=sync_type,
        direction=direction,
        status=status,
        request_payload=request_payload,
        response_payload=response_payload,
        error_message=error_message,
    )


# ============================================================
# PUSH RATES TO CHANNEX
# ============================================================

def push_rates(property_obj, start_date, end_date):
    """
    Push RoomRate rows to Channex using the restrictions endpoint.
    """

    mappings = ChannelMapping.objects.filter(
        provider=ChannelMapping.Provider.CHANNEX,
        property=property_obj,
        room_type__isnull=False,
        rate_plan__isnull=False,
    ).exclude(
        channex_rate_plan_id=""
    )

    if not mappings.exists():
        _log_sync(
            property_obj=property_obj,
            sync_type=SyncLog.SyncType.RATE,
            direction=SyncLog.Direction.OUTBOUND,
            status=SyncLog.Status.FAILED,
            error_message=(
                "No Channex ChannelMapping configured "
                "with rate_plan IDs."
            ),
        )
        return

    values = []

    for mapping in mappings:

        rates = RoomRate.objects.filter(
            room_type=mapping.room_type,
            rate_plan=mapping.rate_plan,
            date__range=(start_date, end_date),
        )

        for rate in rates:

            values.append(
                {
                    "property_id": mapping.channex_property_id,
                    "rate_plan_id": mapping.channex_rate_plan_id,
                    "date": rate.date.isoformat(),
                    "rate": str(rate.base_price),
                }
            )

    payload = {
        "values": values
    }

    try:

        headers = _get_headers()

        response = requests.post(
            f"{settings.CHANNEX_API_BASE_URL}/restrictions",
            json=payload,
            headers=headers,
            timeout=15,
        )

        response.raise_for_status()

        response_data = (
            response.json()
            if response.content
            else {}
        )

        _log_sync(
            property_obj=property_obj,
            sync_type=SyncLog.SyncType.RATE,
            direction=SyncLog.Direction.OUTBOUND,
            status=SyncLog.Status.SUCCESS,
            request_payload=payload,
            response_payload=response_data,
        )

        return response_data

    except ChannexNotConfiguredError as e:

        _log_sync(
            property_obj=property_obj,
            sync_type=SyncLog.SyncType.RATE,
            direction=SyncLog.Direction.OUTBOUND,
            status=SyncLog.Status.FAILED,
            request_payload=payload,
            error_message=str(e),
        )

    except requests.RequestException as e:

        error_detail = (
            e.response.text
            if e.response is not None
            else str(e)
        )

        _log_sync(
            property_obj=property_obj,
            sync_type=SyncLog.SyncType.RATE,
            direction=SyncLog.Direction.OUTBOUND,
            status=SyncLog.Status.FAILED,
            request_payload=payload,
            error_message=error_detail,
        )


# ============================================================
# PUSH AVAILABILITY TO CHANNEX
# ============================================================

def push_availability(property_obj, start_date, end_date):
    """
    Push availability counts to Channex.
    """

    mappings = ChannelMapping.objects.filter(
        provider=ChannelMapping.Provider.CHANNEX,
        property=property_obj,
        room_type__isnull=False,
    ).exclude(
        channex_room_type_id=""
    )

    if not mappings.exists():

        _log_sync(
            property_obj=property_obj,
            sync_type=SyncLog.SyncType.AVAILABILITY,
            direction=SyncLog.Direction.OUTBOUND,
            status=SyncLog.Status.FAILED,
            error_message=(
                "No Channex ChannelMapping configured "
                "with room_type IDs."
            ),
        )

        return

    values = []

    for mapping in mappings:

        counts_by_date = (
            Availability.objects.filter(
                room__room_type=mapping.room_type,
                date__range=(start_date, end_date),
                is_available=True,
                is_blocked=False,
            )
            .values("date")
            .annotate(count=Count("room"))
        )

        for row in counts_by_date:

            values.append(
                {
                    "property_id": mapping.channex_property_id,
                    "room_type_id": mapping.channex_room_type_id,
                    "date": row["date"].isoformat(),
                    "availability": row["count"],
                }
            )

    payload = {
        "values": values
    }

    try:

        headers = _get_headers()

        response = requests.post(
            f"{settings.CHANNEX_API_BASE_URL}/availability",
            json=payload,
            headers=headers,
            timeout=15,
        )

        response.raise_for_status()

        response_data = (
            response.json()
            if response.content
            else {}
        )

        _log_sync(
            property_obj=property_obj,
            sync_type=SyncLog.SyncType.AVAILABILITY,
            direction=SyncLog.Direction.OUTBOUND,
            status=SyncLog.Status.SUCCESS,
            request_payload=payload,
            response_payload=response_data,
        )

        return response_data

    except ChannexNotConfiguredError as e:

        _log_sync(
            property_obj=property_obj,
            sync_type=SyncLog.SyncType.AVAILABILITY,
            direction=SyncLog.Direction.OUTBOUND,
            status=SyncLog.Status.FAILED,
            request_payload=payload,
            error_message=str(e),
        )

    except requests.RequestException as e:

        error_detail = (
            e.response.text
            if e.response is not None
            else str(e)
        )

        _log_sync(
            property_obj=property_obj,
            sync_type=SyncLog.SyncType.AVAILABILITY,
            direction=SyncLog.Direction.OUTBOUND,
            status=SyncLog.Status.FAILED,
            request_payload=payload,
            error_message=error_detail,
        )


# ============================================================
# GET COMPLETE BOOKING FROM CHANNEX
# ============================================================


def get_channex_booking(booking_id):
    """
    Fetch the complete booking from Channex.

    Channex returns:
        data
          └── attributes
                ├── arrival_date
                ├── departure_date
                ├── customer
                ├── rooms
                └── other booking details

    We return the attributes dictionary.
    """

    headers = _get_headers()

    url = (
        f"{settings.CHANNEX_API_BASE_URL}"
        f"/bookings/{booking_id}"
    )

    print("\n=== CHANNEX BOOKING API REQUEST ===")
    print(f"GET: {url}")
    print("===================================\n")

    response = requests.get(
        url,
        headers=headers,
        timeout=15,
    )

    response.raise_for_status()

    response_json = response.json()

    print("\n=== CHANNEX BOOKING API RESPONSE ===")
    print(response_json)
    print("====================================\n")

    data = response_json.get("data", {})

    attributes = data.get("attributes", {})

    if not attributes:
        raise ValueError(
            f"Channex booking {booking_id} "
            f"response does not contain attributes. "
            f"Response: {response_json}"
        )

    return attributes



# ============================================================
# HANDLE CHANNEX BOOKING WEBHOOK
# ============================================================

def handle_channex_booking_webhook(payload):
    """
    Handles a Channex booking webhook.

    Channex sends a small webhook containing:

        property_id
        booking_id
        revision_id

    We then fetch the complete booking from Channex
    using booking_id.
    """

    from datetime import datetime

    from apps.bookings.services import (
        create_booking,
        RoomNotAvailableError,
    )

    from apps.bookings.models import Booking
    from apps.guests.models import Guest
    from apps.properties.models import Room

    # ========================================================
    # 1. READ WEBHOOK PAYLOAD
    # ========================================================

    webhook_data = payload.get(
        "payload",
        {}
    )

    channex_property_id = webhook_data.get(
        "property_id"
    )

    channex_booking_id = webhook_data.get(
        "booking_id"
    )

    revision_id = webhook_data.get(
        "revision_id"
    )

    print("\n=== CHANNEX WEBHOOK DATA ===")
    print(f"Property ID : {channex_property_id}")
    print(f"Booking ID  : {channex_booking_id}")
    print(f"Revision ID : {revision_id}")
    print("============================\n")

    # ========================================================
    # 2. VALIDATE BOOKING ID
    # ========================================================

    if not channex_booking_id:

        raise ValueError(
            "Channex webhook does not contain booking_id."
        )

    if not channex_property_id:

        raise ValueError(
            "Channex webhook does not contain property_id."
        )

    # ========================================================
    # 3. FIND LOCAL CHANNEL MAPPING
    # ========================================================

    mapping = ChannelMapping.objects.filter(
        provider=ChannelMapping.Provider.CHANNEX,
        channex_property_id=channex_property_id,
    ).first()

    if not mapping:

        error_message = (
            f"No ChannelMapping found for Channex "
            f"property {channex_property_id}"
        )

        _log_sync(
            property_obj=None,
            sync_type=SyncLog.SyncType.RESERVATION_IN,
            direction=SyncLog.Direction.INBOUND,
            status=SyncLog.Status.FAILED,
            request_payload=payload,
            error_message=error_message,
        )

        raise ValueError(error_message)

    # ========================================================
    # 4. GET COMPLETE BOOKING FROM CHANNEX
    # ========================================================

    try:

        booking_data = get_channex_booking(
            channex_booking_id
        )

    except ChannexNotConfiguredError as e:

        _log_sync(
            property_obj=mapping.property,
            sync_type=SyncLog.SyncType.RESERVATION_IN,
            direction=SyncLog.Direction.INBOUND,
            status=SyncLog.Status.FAILED,
            request_payload=payload,
            error_message=str(e),
        )

        raise

    except requests.RequestException as e:

        error_detail = (
            e.response.text
            if e.response is not None
            else str(e)
        )

        error_message = (
            f"Failed to fetch Channex booking "
            f"{channex_booking_id}: {error_detail}"
        )

        _log_sync(
            property_obj=mapping.property,
            sync_type=SyncLog.SyncType.RESERVATION_IN,
            direction=SyncLog.Direction.INBOUND,
            status=SyncLog.Status.FAILED,
            request_payload=payload,
            error_message=error_message,
        )

        raise

    # ========================================================
    # 5. PRINT COMPLETE BOOKING FOR DEBUGGING
    # ========================================================

    print("\n=== COMPLETE CHANNEX BOOKING ===")
    print(booking_data)
    print("================================\n")

    # ========================================================
    # 6. HANDLE POSSIBLE RESPONSE WRAPPER
    # ========================================================

    if isinstance(booking_data, dict):

        if "booking" in booking_data:
            booking_data = booking_data["booking"]

        elif "data" in booking_data:

            if isinstance(
                booking_data["data"],
                dict
            ):
                booking_data = booking_data["data"]

    # ========================================================
    # 7. EXTRACT DATES
    # ========================================================

    arrival_date = booking_data.get(
        "arrival_date"
    )

    departure_date = booking_data.get(
        "departure_date"
    )

    if not arrival_date:

        raise ValueError(
            f"Channex booking {channex_booking_id} "
            f"does not contain arrival_date. "
            f"Full response: {booking_data}"
        )

    if not departure_date:

        raise ValueError(
            f"Channex booking {channex_booking_id} "
            f"does not contain departure_date. "
            f"Full response: {booking_data}"
        )

    # ========================================================
    # 8. GET CUSTOMER
    # ========================================================

    customer = booking_data.get(
        "customer",
        {}
    )

    if not isinstance(customer, dict):
        customer = {}

    customer_email = customer.get(
        "mail"
    )

    unique_id = booking_data.get(
        "unique_id",
        channex_booking_id,
    )

    if not customer_email:

        customer_email = (
            f"guest_{unique_id}"
            "@channex.placeholder"
        )

    # ========================================================
    # 9. CREATE / GET GUEST
    # ========================================================

    guest, _ = Guest.objects.get_or_create(
        email=customer_email,
        defaults={
            "first_name": customer.get(
                "name",
                "Guest",
            ),
            "last_name": customer.get(
                "surname",
                "",
            ),
            "phone": customer.get(
                "phone",
                "",
            ),
        },
    )

    # ========================================================
    # 10. FIND LOCAL ROOM
    # ========================================================

    available_room = Room.objects.filter(
        room_type=mapping.room_type,
        is_active=True,
    ).first()

    if not available_room:

        raise RoomNotAvailableError(
            "No active room available for "
            f"room type {mapping.room_type}"
        )

    # ========================================================
    # 11. CREATE LOCAL BOOKING
    # ========================================================

    try:

        booking = create_booking(

            property_obj=mapping.property,

            guest=guest,

            check_in_date=datetime.strptime(
                arrival_date,
                "%Y-%m-%d",
            ).date(),

            check_out_date=datetime.strptime(
                departure_date,
                "%Y-%m-%d",
            ).date(),

            room_requests=[
                {
                    "room_id": available_room.id,

                    "room_type_id": (
                        mapping.room_type_id
                    ),

                    "rate_plan_id": (
                        mapping.rate_plan_id
                    ),

                    "adults": 1,
                }
            ],

            source=Booking.Source.OTHER_OTA,
        )

        # ====================================================
        # 12. SAVE CHANNEX REFERENCE
        # ====================================================

        booking.ota_reference = unique_id

        booking.save(
            update_fields=[
                "ota_reference"
            ]
        )

        # ====================================================
        # 13. LOG SUCCESS
        # ====================================================

        _log_sync(
            property_obj=mapping.property,
            sync_type=SyncLog.SyncType.RESERVATION_IN,
            direction=SyncLog.Direction.INBOUND,
            status=SyncLog.Status.SUCCESS,
            request_payload=payload,
            response_payload={
                "booking_number": (
                    booking.booking_number
                ),
                "channex_booking_id": (
                    channex_booking_id
                ),
            },
        )

        print(
            "\n=== CHANNEX BOOKING CREATED ==="
        )
        print(
            f"Local Booking: "
            f"{booking.booking_number}"
        )
        print(
            f"Channex Booking: "
            f"{channex_booking_id}"
        )
        print(
            "================================\n"
        )

        return booking

    except RoomNotAvailableError as e:

        _log_sync(
            property_obj=mapping.property,
            sync_type=SyncLog.SyncType.RESERVATION_IN,
            direction=SyncLog.Direction.INBOUND,
            status=SyncLog.Status.FAILED,
            request_payload=payload,
            error_message=str(e),
        )

        raise
