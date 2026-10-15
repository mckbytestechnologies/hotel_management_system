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
    # 2. VALIDATE WEBHOOK DATA
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
    # 3. GET COMPLETE BOOKING FROM CHANNEX
    # ========================================================

    try:

        booking_data = get_channex_booking(
            channex_booking_id
        )

    except ChannexNotConfiguredError as e:

        # We cannot determine the local property here
        # because Channex configuration itself failed.

        print(
            "\n=== CHANNEX CONFIGURATION ERROR ==="
        )
        print(str(e))
        print(
            "===================================\n"
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

        print(
            "\n=== CHANNEX BOOKING API ERROR ==="
        )
        print(error_message)
        print(
            "==================================\n"
        )

        # At this point we still may not have a reliable
        # local property object. Do not create a SyncLog
        # with property_obj=None because property_id is NOT NULL.

        raise

    # ========================================================
    # 4. HANDLE POSSIBLE CHANNEX RESPONSE WRAPPER
    # ========================================================

    if isinstance(booking_data, dict):

        if "booking" in booking_data:

            booking_data = booking_data["booking"]

        elif "data" in booking_data:

            if isinstance(
                booking_data["data"],
                dict
            ):

                # Channex API can return:
                #
                # {
                #     "data": {
                #         "attributes": {...}
                #     }
                # }
                #
                # or:
                #
                # {
                #     "data": {...}
                # }

                data = booking_data["data"]

                if "attributes" in data:
                    booking_data = data["attributes"]
                else:
                    booking_data = data

    if not isinstance(booking_data, dict):

        raise ValueError(
            f"Invalid Channex booking response for "
            f"{channex_booking_id}."
        )

    # ========================================================
    # 5. PRINT COMPLETE BOOKING FOR DEBUGGING
    # ========================================================

    print("\n=== COMPLETE CHANNEX BOOKING ===")
    print(booking_data)
    print("================================\n")

    # ========================================================
    # 6. GET BOOKING ROOMS
    # ========================================================

    booking_rooms = booking_data.get(
        "rooms"
    ) or []

    if not booking_rooms:

        raise ValueError(
            f"Channex booking {channex_booking_id} "
            f"does not contain any rooms."
        )

    # For the current implementation we use the first
    # Channex booking room.

    channex_room = booking_rooms[0]

    channex_room_type_id = channex_room.get(
        "room_type_id"
    )

    channex_rate_plan_id = channex_room.get(
        "rate_plan_id"
    )

    if not channex_room_type_id:

        raise ValueError(
            f"Channex booking {channex_booking_id} "
            f"does not contain room_type_id."
        )

    if not channex_rate_plan_id:

        raise ValueError(
            f"Channex booking {channex_booking_id} "
            f"does not contain rate_plan_id."
        )

    print("\n=== CHANNEX ROOM MAPPING ===")
    print(
        f"Room Type ID : "
        f"{channex_room_type_id}"
    )
    print(
        f"Rate Plan ID : "
        f"{channex_rate_plan_id}"
    )
    print("============================\n")

    # ========================================================
    # 7. FIND EXACT LOCAL CHANNEL MAPPING
    # ========================================================

    mapping = ChannelMapping.objects.filter(
        provider=ChannelMapping.Provider.CHANNEX,
        channex_property_id=channex_property_id,
        channex_room_type_id=channex_room_type_id,
        channex_rate_plan_id=channex_rate_plan_id,
    ).select_related(
        "property",
        "room_type",
        "rate_plan",
    ).first()

    # ========================================================
    # 7A. HANDLE MISSING ROOM/RATE MAPPING
    # ========================================================

    if not mapping:

        error_message = (
            f"No ChannelMapping found for Channex booking "
            f"{channex_booking_id}. "
            f"Property={channex_property_id}, "
            f"RoomType={channex_room_type_id}, "
            f"RatePlan={channex_rate_plan_id}"
        )

        print(
            "\n=== CHANNEX MAPPING ERROR ==="
        )
        print(error_message)
        print(
            "=============================\n"
        )

        # ----------------------------------------------------
        # Try to find the local property using only the
        # Channex property ID.
        #
        # This is important because the room type/rate plan
        # may not be mapped yet, but the property itself may
        # already be mapped.
        # ----------------------------------------------------

        property_mapping = ChannelMapping.objects.filter(
            provider=ChannelMapping.Provider.CHANNEX,
            channex_property_id=channex_property_id,
        ).select_related(
            "property"
        ).first()

        local_property = (
            property_mapping.property
            if property_mapping
            else None
        )

        # ----------------------------------------------------
        # Only create SyncLog when we have a valid property.
        #
        # sync_logs.property_id is NOT NULL.
        # ----------------------------------------------------

        if local_property:

            _log_sync(
                property_obj=local_property,
                sync_type=SyncLog.SyncType.RESERVATION_IN,
                direction=SyncLog.Direction.INBOUND,
                status=SyncLog.Status.FAILED,
                request_payload=payload,
                error_message=error_message,
            )

        else:

            print(
                "WARNING: Could not determine local "
                "property for this Channex booking."
            )

            print(
                "SyncLog was NOT created because "
                "property_id cannot be NULL."
            )

        raise ValueError(
            error_message
        )

    # ========================================================
    # 7B. MAPPING FOUND
    # ========================================================

    print(
        "\n=== LOCAL CHANNEL MAPPING FOUND ==="
    )

    print(
        f"Property : "
        f"{mapping.property}"
    )

    print(
        f"Room Type : "
        f"{mapping.room_type}"
    )

    print(
        f"Rate Plan : "
        f"{mapping.rate_plan}"
    )

    print(
        "====================================\n"
    )

    # ========================================================
    # 8. EXTRACT OTA REFERENCE
    # ========================================================

    unique_id = booking_data.get(
        "unique_id",
        channex_booking_id,
    )

    # ========================================================
    # 9. PREVENT DUPLICATE BOOKINGS
    # ========================================================

    existing_booking = Booking.objects.filter(
        ota_reference=unique_id
    ).first()

    if existing_booking:

        print(
            "\n=== CHANNEX BOOKING ALREADY EXISTS ==="
        )

        print(
            f"Local Booking : "
            f"{existing_booking.booking_number}"
        )

        print(
            f"OTA Reference : "
            f"{unique_id}"
        )

        print(
            "=======================================\n"
        )

        return existing_booking

    # ========================================================
    # 10. EXTRACT DATES
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
    # 11. GET CUSTOMER
    # ========================================================

    customer = booking_data.get(
        "customer",
        {}
    )

    if not isinstance(
        customer,
        dict
    ):

        customer = {}

    customer_email = customer.get(
        "mail"
    )

    if not customer_email:

        customer_email = (
            f"guest_{unique_id}"
            "@channex.placeholder"
        )

    # ========================================================
    # 12. CREATE / GET GUEST
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
    # 13. GET OCCUPANCY
    # ========================================================

    room_occupancy = (
        channex_room.get(
            "occupancy"
        )
        or {}
    )

    adults = room_occupancy.get(
        "adults"
    ) or 1

    children = room_occupancy.get(
        "children"
    ) or 0

    print("\n=== CHANNEX OCCUPANCY ===")
    print(f"Adults   : {adults}")
    print(f"Children : {children}")
    print("==========================\n")

    # ========================================================
    # 14. FIND LOCAL ROOM
    # ========================================================

    available_room = Room.objects.filter(
        room_type=mapping.room_type,
        is_active=True,
    ).first()

    if not available_room:

        error_message = (
            "No active room available for "
            f"room type {mapping.room_type}"
        )

        _log_sync(
            property_obj=mapping.property,
            sync_type=SyncLog.SyncType.RESERVATION_IN,
            direction=SyncLog.Direction.INBOUND,
            status=SyncLog.Status.FAILED,
            request_payload=payload,
            error_message=error_message,
        )

        raise RoomNotAvailableError(
            error_message
        )

    # ========================================================
    # 15. CREATE LOCAL BOOKING
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

                    "adults": adults,

                    "children": children,
                }
            ],

            source=Booking.Source.BOOKING_COM,

            adults=adults,

            children=children,
        )

        # ====================================================
        # 16. SAVE CHANNEX REFERENCE
        # ====================================================

        booking.ota_reference = unique_id

        booking.save(
            update_fields=[
                "ota_reference"
            ]
        )

        # ====================================================
        # 17. LOG SUCCESS
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
                "channex_unique_id": (
                    unique_id
                ),
            },
        )

        # ====================================================
        # 18. DEBUG OUTPUT
        # ====================================================

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
            f"OTA Reference: "
            f"{unique_id}"
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


def pull_rates_from_channex(property_obj, start_date, end_date):
    """
    Reads current rates from Channex and writes them into our RoomRate
    table. Mirrors the STAAH pull_rates_from_staah() function — this lets
    us test the whole "external system is the source of truth for
    pricing" pattern against Channex's real, working sandbox right now,
    without waiting on STAAH credentials.
    """
    from apps.availability.models import RoomRate

    mappings = ChannelMapping.objects.filter(
        provider=ChannelMapping.Provider.CHANNEX,
        property=property_obj, room_type__isnull=False, rate_plan__isnull=False,
    ).exclude(channex_rate_plan_id='')

    if not mappings.exists():
        _log_sync(
            property_obj=property_obj, sync_type=SyncLog.SyncType.RATE,
            direction=SyncLog.Direction.INBOUND, status=SyncLog.Status.FAILED,
            error_message="No Channex ChannelMapping configured for this property."
        )
        return 0

    try:
        headers = _get_headers()
    except ChannexNotConfiguredError as e:
        _log_sync(
            property_obj=property_obj, sync_type=SyncLog.SyncType.RATE,
            direction=SyncLog.Direction.INBOUND, status=SyncLog.Status.FAILED,
            error_message=str(e),
        )
        return 0

    updated_count = 0

    for mapping in mappings:
        params = {
            'filter[property_id]': mapping.channex_property_id,
            'filter[rate_plan_id]': mapping.channex_rate_plan_id,
            'filter[date][gte]': start_date.isoformat(),
            'filter[date][lte]': end_date.isoformat(),
            'filter[restrictions]': 'rate',
        }
        try:
            response = requests.get(
                f"{settings.CHANNEX_API_BASE_URL}/restrictions",
                params=params, headers=headers, timeout=15,
            )
            response.raise_for_status()
            data = response.json()

            rate_data = data.get('data', {})

            rate_plan_data = rate_data.get(
                mapping.channex_rate_plan_id,
                {}
            )

            for row_date, row in rate_plan_data.items():
                rate = row.get('rate')

                if rate is None:
                    continue

                RoomRate.objects.update_or_create(
                    property=property_obj,
                    room_type=mapping.room_type,
                    rate_plan=mapping.rate_plan,
                    date=row_date,
                    defaults={
                        'base_price': rate,
                    },
                )

                updated_count += 1

            _log_sync(
                property_obj=property_obj, sync_type=SyncLog.SyncType.RATE,
                direction=SyncLog.Direction.INBOUND, status=SyncLog.Status.SUCCESS,
                request_payload=params, response_payload={'count': updated_count},
            )
        except requests.RequestException as e:
            error_detail = e.response.text if e.response is not None else str(e)
            _log_sync(
                property_obj=property_obj, sync_type=SyncLog.SyncType.RATE,
                direction=SyncLog.Direction.INBOUND, status=SyncLog.Status.FAILED,
                request_payload=params, error_message=error_detail,
            )

    return updated_count

def sync_rooms_from_channex(property_obj, channex_property_id):
    """
    Pulls every room type and rate plan Channex has for this property,
    creates matching local RoomType/RatePlan records if they don't
    already exist, and creates the ChannelMapping row linking each
    Channex room_type+rate_plan pair to our local records.

    This is what makes 'integrate all the rooms from channel' a single
    call instead of manually creating ChannelMapping rows one at a time
    for every room type Channex has.
    """
    from apps.properties.models import RoomType, RatePlan

    try:
        headers = _get_headers()
    except ChannexNotConfiguredError as e:
        _log_sync(
            property_obj=property_obj, sync_type=SyncLog.SyncType.AVAILABILITY,
            direction=SyncLog.Direction.INBOUND, status=SyncLog.Status.FAILED,
            error_message=str(e),
        )
        return {'room_types_created': 0, 'rate_plans_created': 0, 'mappings_created': 0}

    # --- 1. Fetch all room types for this Channex property ---
    rt_response = requests.get(
        f"{settings.CHANNEX_API_BASE_URL}/room_types",
        params={'filter[property_id]': channex_property_id},
        headers=headers, timeout=15,
    )
    rt_response.raise_for_status()
    channex_room_types = rt_response.json().get('data', [])

    # --- 2. Fetch all rate plans for this Channex property ---
    rp_response = requests.get(
        f"{settings.CHANNEX_API_BASE_URL}/rate_plans",
        params={'filter[property_id]': channex_property_id},
        headers=headers, timeout=15,
    )
    rp_response.raise_for_status()
    channex_rate_plans = rp_response.json().get('data', [])

    room_types_created = 0
    rate_plans_created = 0
    mappings_created = 0

    # --- 3. Create/find local RoomType for each Channex room type ---
    # Keyed by Channex room_type_id so we can look it up when wiring rate plans.
    local_room_type_by_channex_id = {}

    for rt in channex_room_types:
        attrs = rt.get('attributes', {})
        channex_rt_id = rt.get('id')
        title = attrs.get('title', 'Untitled Room')
        max_occupancy = attrs.get('occ_adults', 2) + attrs.get('occ_children', 0)

        # Reuse an existing mapping if this room type was already synced before.
        existing_mapping = ChannelMapping.objects.filter(
            provider=ChannelMapping.Provider.CHANNEX,
            property=property_obj,
            channex_room_type_id=channex_rt_id,
        ).exclude(room_type__isnull=True).first()

        if existing_mapping:
            local_room_type_by_channex_id[channex_rt_id] = existing_mapping.room_type
            continue

        room_type, created = RoomType.objects.get_or_create(
            property=property_obj,
            code=f"CHX-{channex_rt_id[:8]}",
            defaults={
                'name': title,
                'max_adults': attrs.get('occ_adults', 2),
                'max_children': attrs.get('occ_children', 0),
                'max_occupancy': max_occupancy,
                'base_occupancy': attrs.get('default_occupancy', 1),
            },
        )
        if created:
            room_types_created += 1
        local_room_type_by_channex_id[channex_rt_id] = room_type

    # --- 4. Create/find local RatePlan for each Channex rate plan ---
    local_rate_plan_by_channex_id = {}

    for rp in channex_rate_plans:
        attrs = rp.get('attributes', {})
        channex_rp_id = rp.get('id')
        title = attrs.get('title', 'Untitled Rate Plan')
        meal_type = attrs.get('meal_type', 'none')

        existing_mapping = ChannelMapping.objects.filter(
            provider=ChannelMapping.Provider.CHANNEX,
            property=property_obj,
            channex_rate_plan_id=channex_rp_id,
        ).exclude(rate_plan__isnull=True).first()

        if existing_mapping:
            local_rate_plan_by_channex_id[channex_rp_id] = existing_mapping.rate_plan
            continue

        rate_plan, created = RatePlan.objects.get_or_create(
            property=property_obj,
            code=f"CHX-{channex_rp_id[:8]}",
            defaults={
                'name': title,
                'meal_plan': meal_type if meal_type != 'none' else '',
                'is_refundable': True,  # Channex didn't give us this on the list endpoint; adjust if needed
            },
        )
        if created:
            rate_plans_created += 1
        local_rate_plan_by_channex_id[channex_rp_id] = rate_plan

    # --- 5. Create ChannelMapping rows linking each room_type to its rate plan(s) ---
    # Channex's rate_plan list includes a `room_type` relationship telling us
    # which room type each rate plan belongs to.
    for rp in channex_rate_plans:
        channex_rp_id = rp.get('id')
        relationships = rp.get('relationships', {})
        room_type_rel = relationships.get('room_type', {}).get('data', {})
        channex_rt_id = room_type_rel.get('id')

        if not channex_rt_id or channex_rt_id not in local_room_type_by_channex_id:
            continue
        if channex_rp_id not in local_rate_plan_by_channex_id:
            continue

        local_room_type = local_room_type_by_channex_id[channex_rt_id]
        local_rate_plan = local_rate_plan_by_channex_id[channex_rp_id]

        mapping, created = ChannelMapping.objects.get_or_create(
            provider=ChannelMapping.Provider.CHANNEX,
            property=property_obj,
            room_type=local_room_type,
            rate_plan=local_rate_plan,
            defaults={
                'channex_property_id': channex_property_id,
                'channex_room_type_id': channex_rt_id,
                'channex_rate_plan_id': channex_rp_id,
            },
        )
        if created:
            mappings_created += 1

    result = {
        'room_types_created': room_types_created,
        'rate_plans_created': rate_plans_created,
        'mappings_created': mappings_created,
    }

    _log_sync(
        property_obj=property_obj, sync_type=SyncLog.SyncType.AVAILABILITY,
        direction=SyncLog.Direction.INBOUND, status=SyncLog.Status.SUCCESS,
        request_payload={'channex_property_id': channex_property_id},
        response_payload=result,
    )

    return result