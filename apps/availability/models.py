from django.db import models
from apps.core.models import BaseModel
from apps.properties.models import Property, RoomType, RatePlan, Room


class RoomRate(BaseModel):
    """
    The actual sellable nightly price for a RoomType under a specific RatePlan,
    on a specific date. This is what STAAH/OTAs pull when they ask "what's the
    rate for Deluxe Room, Standard Rate, on 2026-12-25?"
    """
    property = models.ForeignKey(Property, on_delete=models.CASCADE, related_name='room_rates')
    room_type = models.ForeignKey(RoomType, on_delete=models.CASCADE, related_name='rates')
    rate_plan = models.ForeignKey(RatePlan, on_delete=models.CASCADE, related_name='rates')
    date = models.DateField(db_index=True)
    base_price = models.DecimalField(max_digits=10, decimal_places=2)
    extra_adult_price = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    extra_child_price = models.DecimalField(max_digits=10, decimal_places=2, default=0)

    class Meta:
        db_table = 'room_rates'
        verbose_name = 'Room Rate'
        verbose_name_plural = 'Room Rates'
        ordering = ['date']
        unique_together = [('room_type', 'rate_plan', 'date')]
        indexes = [
            models.Index(fields=['room_type', 'rate_plan', 'date']),
        ]

    def __str__(self):
        return f"{self.room_type} / {self.rate_plan} - {self.date} - {self.base_price}"


class SeasonalRate(BaseModel):
    """
    A named date-range price override (e.g. 'Christmas Peak', 'Monsoon Discount').
    Applied as a multiplier or flat override on top of RoomRate's base_price
    when generating rates in bulk — kept separate so staff can define a season
    once and regenerate RoomRate rows for that range, rather than editing
    hundreds of individual date rows by hand.
    """
    class AdjustmentType(models.TextChoices):
        PERCENTAGE = 'PERCENTAGE', 'Percentage Increase/Decrease'
        FLAT = 'FLAT', 'Flat Amount Increase/Decrease'
        OVERRIDE = 'OVERRIDE', 'Fixed Price Override'

    property = models.ForeignKey(Property, on_delete=models.CASCADE, related_name='seasonal_rates')
    room_type = models.ForeignKey(RoomType, on_delete=models.CASCADE, related_name='seasonal_rates')
    rate_plan = models.ForeignKey(RatePlan, on_delete=models.CASCADE, related_name='seasonal_rates')
    name = models.CharField(max_length=255)
    start_date = models.DateField()
    end_date = models.DateField()
    adjustment_type = models.CharField(max_length=20, choices=AdjustmentType.choices)
    adjustment_value = models.DecimalField(max_digits=10, decimal_places=2)

    class Meta:
        db_table = 'seasonal_rates'
        verbose_name = 'Seasonal Rate'
        verbose_name_plural = 'Seasonal Rates'
        ordering = ['start_date']

    def __str__(self):
        return f"{self.name} ({self.start_date} to {self.end_date})"

    def clean(self):
        from django.core.exceptions import ValidationError
        if self.end_date < self.start_date:
            raise ValidationError("end_date cannot be before start_date.")


class Restriction(BaseModel):
    """
    Per-date booking rules for a RoomType+RatePlan. This is what STAAH/OTAs
    need to enforce things like 'minimum 2-night stay over New Year' or
    'closed to arrival on Mondays'.
    """
    property = models.ForeignKey(Property, on_delete=models.CASCADE, related_name='restrictions')
    room_type = models.ForeignKey(RoomType, on_delete=models.CASCADE, related_name='restrictions')
    rate_plan = models.ForeignKey(RatePlan, on_delete=models.CASCADE, related_name='restrictions')
    date = models.DateField(db_index=True)
    min_stay = models.PositiveSmallIntegerField(default=1)
    max_stay = models.PositiveSmallIntegerField(null=True, blank=True)
    closed_to_arrival = models.BooleanField(default=False)
    closed_to_departure = models.BooleanField(default=False)
    stop_sell = models.BooleanField(default=False)  # no new bookings allowed for this date at all

    class Meta:
        db_table = 'restrictions'
        verbose_name = 'Restriction'
        verbose_name_plural = 'Restrictions'
        ordering = ['date']
        unique_together = [('room_type', 'rate_plan', 'date')]

    def __str__(self):
        return f"{self.room_type} - {self.date}"


class Availability(BaseModel):
    """
    Per-Room, per-Date inventory record. This is the single source of truth
    for "is this specific room bookable on this specific date" — separate
    from Room.status (which reflects real-time operational state like
    Occupied/Maintenance) because a room can be operationally Available
    but manually blocked out of sale for a date range (e.g. renovation
    scheduled next month), or vice-versa.
    """
    property = models.ForeignKey(Property, on_delete=models.CASCADE, related_name='availabilities')
    room = models.ForeignKey(Room, on_delete=models.CASCADE, related_name='availabilities')
    date = models.DateField(db_index=True)
    is_available = models.BooleanField(default=True)
    is_blocked = models.BooleanField(default=False)  # manual block: maintenance, owner-use, etc.
    block_reason = models.CharField(max_length=255, blank=True)
    booking_room = models.ForeignKey(
        'bookings.BookingRoom', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='availability_records'
    )

    class Meta:
        db_table = 'availability'
        verbose_name = 'Availability'
        verbose_name_plural = 'Availability'
        ordering = ['date']
        unique_together = [('room', 'date')]
        indexes = [
            models.Index(fields=['room', 'date']),
            models.Index(fields=['property', 'date', 'is_available']),
        ]

    def __str__(self):
        return f"{self.room} - {self.date} - {'Available' if self.is_available and not self.is_blocked else 'Blocked'}"

        def is_bookable(self):
            return self.is_available and not self.is_blocked