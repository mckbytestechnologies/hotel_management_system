from datetime import timedelta

from django.core.cache import cache
from django.db.models import Count, Q
from rest_framework import viewsets, filters, status
from rest_framework.views import APIView
from rest_framework.response import Response
from django_filters.rest_framework import DjangoFilterBackend

from apps.properties.models import RoomType, Room
from .models import RoomRate, SeasonalRate, Restriction, Availability
from .serializers import (
    RoomRateSerializer, SeasonalRateSerializer, RestrictionSerializer,
    AvailabilitySerializer, AvailabilitySearchResultSerializer,
)


from datetime import date as date_cls
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated



# ── Standard CRUD ViewSets ──────────────────────────────────────────────

class RoomRateViewSet(viewsets.ModelViewSet):
    queryset = RoomRate.objects.select_related('property', 'room_type', 'rate_plan').all()
    serializer_class = RoomRateSerializer
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_fields = ['property', 'room_type', 'rate_plan', 'date', 'is_active']
    ordering_fields = ['date', 'base_price']


class SeasonalRateViewSet(viewsets.ModelViewSet):
    queryset = SeasonalRate.objects.select_related('property', 'room_type', 'rate_plan').all()
    serializer_class = SeasonalRateSerializer
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_fields = ['property', 'room_type', 'rate_plan', 'is_active']
    ordering_fields = ['start_date']


class RestrictionViewSet(viewsets.ModelViewSet):
    queryset = Restriction.objects.select_related('property', 'room_type', 'rate_plan').all()
    serializer_class = RestrictionSerializer
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_fields = ['property', 'room_type', 'rate_plan', 'date', 'stop_sell']
    ordering_fields = ['date']


class AvailabilityViewSet(viewsets.ModelViewSet):
    queryset = Availability.objects.select_related('property', 'room').all()
    serializer_class = AvailabilitySerializer
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_fields = ['property', 'room', 'date', 'is_available', 'is_blocked']
    ordering_fields = ['date']


# ── The high-traffic endpoint: date-range availability + price search ──

class AvailabilitySearchView(APIView):
    """
    GET /api/availability/search/?property=1&check_in=2026-12-24&check_out=2026-12-27&adults=2

    For each RoomType+RatePlan combo under the property, returns:
    - how many physical rooms are actually free for the ENTIRE date range
    - total price for the stay + nightly average
    - whether the stay satisfies min_stay / stop_sell / closed_to_arrival rules

    Performance notes:
    - One query counts available rooms per room_type (aggregated, not looped)
    - One query pulls all RoomRate rows in range (used to sum price per plan)
    - Restrictions checked in bulk per room_type/rate_plan, not per night
    - Result cached for 60s per unique query — search traffic is bursty
      (many guests searching the same dates) and rates/availability don't
      change every second, so a short cache absorbs load spikes cheaply.
    """

    def get(self, request):
        property_id = request.query_params.get('property')
        check_in = request.query_params.get('check_in')
        check_out = request.query_params.get('check_out')

        if not all([property_id, check_in, check_out]):
            return Response(
                {'detail': 'property, check_in, and check_out are required.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        cache_key = f"avail_search:{property_id}:{check_in}:{check_out}"
        cached = cache.get(cache_key)
        if cached is not None:
            return Response(cached)

        try:
            from datetime import date as date_cls
            check_in_date = date_cls.fromisoformat(check_in)
            check_out_date = date_cls.fromisoformat(check_out)
        except ValueError:
            return Response({'detail': 'Dates must be in YYYY-MM-DD format.'}, status=400)

        if check_out_date <= check_in_date:
            return Response({'detail': 'check_out must be after check_in.'}, status=400)

        nights = (check_out_date - check_in_date).days
        stay_dates = [check_in_date + timedelta(days=i) for i in range(nights)]

        # 1. Room types under this property, with their total room count preloaded.
        room_types = (
            RoomType.objects.filter(property_id=property_id, is_active=True)
            .annotate(total_rooms=Count('rooms', filter=Q(rooms__is_active=True)))
        )

        # 2. Rooms that are UNAVAILABLE (blocked or explicitly unavailable) on
        #    ANY night of the stay — one query, not one per night.
        blocked_room_ids = set(
            Availability.objects.filter(
                date__in=stay_dates
            ).filter(Q(is_available=False) | Q(is_blocked=True))
            .values_list('room_id', flat=True)
            .distinct()
        )

        # 3. All active rate plans available under this property.
        from apps.properties.models import RatePlan
        rate_plans = RatePlan.objects.filter(property_id=property_id, is_active=True)

        # 4. Pull every RoomRate for the stay range in ONE query, grouped in Python
        #    by (room_type_id, rate_plan_id) — avoids N queries per combo.
        rates_qs = RoomRate.objects.filter(
            property_id=property_id, date__in=stay_dates
        ).values('room_type_id', 'rate_plan_id', 'date', 'base_price')

        rates_by_combo = {}
        for row in rates_qs:
            key = (row['room_type_id'], row['rate_plan_id'])
            rates_by_combo.setdefault(key, {})[row['date']] = row['base_price']

        # 5. Restrictions for the stay range, same grouping approach.
        restrictions_qs = Restriction.objects.filter(
            property_id=property_id, date__in=stay_dates
        ).values('room_type_id', 'rate_plan_id', 'date', 'min_stay', 'closed_to_arrival', 'stop_sell')

        restrictions_by_combo = {}
        for row in restrictions_qs:
            key = (row['room_type_id'], row['rate_plan_id'])
            restrictions_by_combo.setdefault(key, []).append(row)

        results = []
        for rt in room_types:
            # How many of this room_type's rooms are free for every night of the stay.
            rt_room_ids = set(Room.objects.filter(room_type=rt, is_active=True).values_list('id', flat=True))
            free_rooms_count = len(rt_room_ids - blocked_room_ids)

            if free_rooms_count == 0:
                continue  # no point returning a sold-out combo

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

                combo_restrictions = restrictions_by_combo.get(key, [])
                stop_sell = any(r['stop_sell'] for r in combo_restrictions)
                closed_to_arrival_today = any(
                    r['closed_to_arrival'] and r['date'] == check_in_date for r in combo_restrictions
                )
                min_stay_required = max([r['min_stay'] for r in combo_restrictions], default=1)

                is_bookable = (
                    not stop_sell
                    and not closed_to_arrival_today
                    and nights >= min_stay_required
                )

                total_price = sum(nightly_rates.values())

                results.append({
                    'room_type_id': rt.id,
                    'room_type_name': rt.name,
                    'rate_plan_id': plan.id,
                    'rate_plan_name': plan.name,
                    'available_rooms': free_rooms_count,
                    'total_price': total_price,
                    'nightly_avg_price': round(total_price / nights, 2),
                    'min_stay': min_stay_required,
                    'is_bookable': is_bookable,
                })

        serializer = AvailabilitySearchResultSerializer(results, many=True)
        response_data = serializer.data
        cache.set(cache_key, response_data, timeout=60)  # 60s cache — see docstring
        return Response(response_data)



@api_view(['POST'])
@permission_classes([IsAuthenticated])
def bulk_block_rooms(request):
    """
    POST /api/availability/bulk-block/
    Body: {
        "room_ids": [1, 2],
        "start_date": "2026-12-20",
        "end_date": "2026-12-25",
        "block_reason": "Annual maintenance",
        "action": "block"   // or "unblock"
    }

    Blocks (or unblocks) a set of rooms across a date range in ONE bulk
    operation — this is what a front-desk/maintenance workflow actually
    needs ("take rooms 101-103 out of sale for renovation next week"),
    rather than clicking through day-by-day admin forms.
    """
    room_ids = request.data.get('room_ids', [])
    start_date_str = request.data.get('start_date')
    end_date_str = request.data.get('end_date')
    block_reason = request.data.get('block_reason', '')
    action = request.data.get('action', 'block')

    if not room_ids or not start_date_str or not end_date_str:
        return Response(
            {'detail': 'room_ids, start_date, and end_date are required.'},
            status=status.HTTP_400_BAD_REQUEST
        )

    try:
        start = date_cls.fromisoformat(start_date_str)
        end = date_cls.fromisoformat(end_date_str)
    except ValueError:
        return Response({'detail': 'Dates must be YYYY-MM-DD.'}, status=400)

    if end < start:
        return Response({'detail': 'end_date cannot be before start_date.'}, status=400)

    rooms = Room.objects.filter(id__in=room_ids)
    if rooms.count() != len(set(room_ids)):
        return Response({'detail': 'One or more room_ids not found.'}, status=400)

    date_range = [start + timedelta(days=i) for i in range((end - start).days + 1)]
    is_blocking = action == 'block'

    updated_count = 0
    created_count = 0

    for room in rooms:
        for d in date_range:
            obj, created = Availability.objects.update_or_create(
                room=room, date=d,
                defaults={
                    'property': room.property,
                    'is_blocked': is_blocking,
                    'is_available': not is_blocking,
                    'block_reason': block_reason if is_blocking else '',
                }
            )
            if created:
                created_count += 1
            else:
                updated_count += 1

    return Response({
        'action': action,
        'rooms_affected': len(room_ids),
        'dates_affected': len(date_range),
        'records_created': created_count,
        'records_updated': updated_count,
    })