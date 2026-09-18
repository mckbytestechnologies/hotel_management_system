from django.db import models
from apps.core.models import BaseModel


class Property(BaseModel):
    """
    A hotel/property. Root of the entire hierarchy.
    `code` is the short unique identifier used later for STAAH property mapping.
    """
    name = models.CharField(max_length=255)
    code = models.CharField(max_length=20, unique=True, db_index=True)
    address = models.CharField(max_length=500)
    city = models.CharField(max_length=100)
    state = models.CharField(max_length=100)
    country = models.CharField(max_length=100)
    phone = models.CharField(max_length=20, blank=True)
    email = models.EmailField(blank=True)
    check_in_time = models.TimeField(default='12:00:00')
    check_out_time = models.TimeField(default='11:00:00')
    tax_number = models.CharField(max_length=50, blank=True)

    class Meta:
        db_table = 'properties'
        verbose_name = 'Property'
        verbose_name_plural = 'Properties'
        ordering = ['name']

    def __str__(self):
        return f"{self.name} ({self.code})"


class RoomType(BaseModel):
    property = models.ForeignKey(
        Property, on_delete=models.CASCADE, related_name='room_types'
    )
    name = models.CharField(max_length=255)
    code = models.CharField(max_length=20, db_index=True)
    description = models.TextField(blank=True)
    max_adults = models.PositiveSmallIntegerField(default=2)
    max_children = models.PositiveSmallIntegerField(default=0)
    max_occupancy = models.PositiveSmallIntegerField(default=2)
    base_occupancy = models.PositiveSmallIntegerField(default=2)
    default_price = models.DecimalField(
        max_digits=10, decimal_places=2, default=0,
        help_text="Fixed nightly price used when no date-specific RoomRate exists."
    )

    class Meta:
        db_table = 'room_types'
        verbose_name = 'Room Type'
        verbose_name_plural = 'Room Types'
        ordering = ['property', 'name']
        unique_together = [('property', 'code')]

    def __str__(self):
        return f"{self.property.code} - {self.name}"


class Room(BaseModel):
    """
    A physical, individually bookable room. Belongs to a RoomType.
    Status here tracks the room's real-world operational state
    (separate from booking-level availability, which lives in `availability` app).
    """

    class RoomStatus(models.TextChoices):
        AVAILABLE = 'AVAILABLE', 'Available'
        OCCUPIED = 'OCCUPIED', 'Occupied'
        RESERVED = 'RESERVED', 'Reserved'
        BLOCKED = 'BLOCKED', 'Blocked'
        MAINTENANCE = 'MAINTENANCE', 'Maintenance'
        OUT_OF_SERVICE = 'OUT_OF_SERVICE', 'Out of Service'

    property = models.ForeignKey(
        Property, on_delete=models.CASCADE, related_name='rooms'
    )
    room_type = models.ForeignKey(
        RoomType, on_delete=models.CASCADE, related_name='rooms'
    )
    room_number = models.CharField(max_length=20)
    floor = models.CharField(max_length=20, blank=True)
    status = models.CharField(
        max_length=20, choices=RoomStatus.choices, default=RoomStatus.AVAILABLE
    )

    class Meta:
        db_table = 'rooms'
        verbose_name = 'Room'
        verbose_name_plural = 'Rooms'
        ordering = ['property', 'room_type', 'room_number']
        unique_together = [('property', 'room_number')]

    def __str__(self):
        return f"{self.room_type.name} - Room {self.room_number}"


class RatePlan(BaseModel):
    """
    A sellable rate plan (e.g. "Standard Rate - Breakfast Included - Non Refundable").
    Rates themselves live in RoomRate (Day 1 diagram) — this is just the plan definition.
    """
    property = models.ForeignKey(
        Property, on_delete=models.CASCADE, related_name='rate_plans'
    )
    name = models.CharField(max_length=255)
    code = models.CharField(max_length=20, db_index=True)
    description = models.TextField(blank=True)
    meal_plan = models.CharField(max_length=100, blank=True)
    cancellation_policy = models.TextField(blank=True)
    is_refundable = models.BooleanField(default=True)

    class Meta:
        db_table = 'rate_plans'
        verbose_name = 'Rate Plan'
        verbose_name_plural = 'Rate Plans'
        ordering = ['property', 'name']
        unique_together = [('property', 'code')]

    def __str__(self):
        return f"{self.property.code} - {self.name}"