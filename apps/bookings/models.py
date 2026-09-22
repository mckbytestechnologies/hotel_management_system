from django.db import models
from apps.core.models import BaseModel
from apps.properties.models import Property, RoomType, Room, RatePlan
from apps.guests.models import Guest


class Booking(BaseModel):
    """
    The reservation header. One Booking can cover multiple rooms
    (see BookingRoom) and multiple nights, but always one guest as
    the primary contact and one check-in/check-out window.
    """
    class Status(models.TextChoices):
        PENDING = 'PENDING', 'Pending'          # created, payment/confirmation not finalized
        CONFIRMED = 'CONFIRMED', 'Confirmed'
        CHECKED_IN = 'CHECKED_IN', 'Checked In'
        CHECKED_OUT = 'CHECKED_OUT', 'Checked Out'
        CANCELLED = 'CANCELLED', 'Cancelled'
        NO_SHOW = 'NO_SHOW', 'No Show'

    class Source(models.TextChoices):
        DIRECT = 'DIRECT', 'Direct / Front Desk'
        WEBSITE = 'WEBSITE', 'Website'
        BOOKING_COM = 'BOOKING_COM', 'Booking.com'
        AGODA = 'AGODA', 'Agoda'
        EXPEDIA = 'EXPEDIA', 'Expedia'
        OTHER_OTA = 'OTHER_OTA', 'Other OTA'

    booking_number = models.CharField(max_length=30, unique=True, db_index=True)
    property = models.ForeignKey(Property, on_delete=models.CASCADE, related_name='bookings')
    guest = models.ForeignKey(Guest, on_delete=models.PROTECT, related_name='bookings')
    check_in_date = models.DateField(db_index=True)
    check_out_date = models.DateField(db_index=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    source = models.CharField(max_length=20, choices=Source.choices, default=Source.DIRECT)
    adults = models.PositiveSmallIntegerField(default=1)
    children = models.PositiveSmallIntegerField(default=0)
    special_requests = models.TextField(blank=True)

    # Denormalized totals — recalculated whenever BookingRoom rows change.
    # Kept here (rather than always summing on the fly) so listing bookings
    # doesn't require aggregating child rows on every request.
    total_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    paid_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)

    # OTA integration fields — populated once STAAH sync is built.
    ota_reference = models.CharField(max_length=100, blank=True, db_index=True)

    cancelled_at = models.DateTimeField(null=True, blank=True)
    cancellation_reason = models.TextField(blank=True)

    class Meta:
        db_table = 'bookings'
        verbose_name = 'Booking'
        verbose_name_plural = 'Bookings'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['property', 'check_in_date', 'check_out_date']),
            models.Index(fields=['status']),
        ]

    def __str__(self):
        return f"{self.booking_number} - {self.guest.full_name}"

    def nights(self):
        """Call as a method — .nights() — since `property` is a field name
        on this model, shadowing Python's @property decorator here."""
        return (self.check_out_date - self.check_in_date).days

    def balance_due(self):
        """Call as a method — .balance_due() — same reason as nights()."""
        return self.total_amount - self.paid_amount


class BookingRoom(BaseModel):
    """
    One specific room reserved within a Booking. A booking with 2 rooms
    for the same dates has 2 BookingRoom rows. This is the row that
    actually links to Availability records to block out inventory.
    """
    booking = models.ForeignKey(Booking, on_delete=models.CASCADE, related_name='booking_rooms')
    room = models.ForeignKey(Room, on_delete=models.PROTECT, related_name='booking_rooms')
    room_type = models.ForeignKey(RoomType, on_delete=models.PROTECT, related_name='booking_rooms')
    rate_plan = models.ForeignKey(RatePlan, on_delete=models.PROTECT, related_name='booking_rooms')
    check_in_date = models.DateField()
    check_out_date = models.DateField()
    rate_amount = models.DecimalField(max_digits=10, decimal_places=2)  # total for this room's stay
    adults = models.PositiveSmallIntegerField(default=1)
    children = models.PositiveSmallIntegerField(default=0)

    class Meta:
        db_table = 'booking_rooms'
        verbose_name = 'Booking Room'
        verbose_name_plural = 'Booking Rooms'
        ordering = ['check_in_date']

    def __str__(self):
        return f"{self.booking.booking_number} - {self.room}"

class Payment(BaseModel):
    """
    A single payment transaction against a Booking. A booking can have
    multiple Payment rows (deposit, balance, split payments, failed
    attempts kept for audit trail).
    """
    class Method(models.TextChoices):
        CASH = 'CASH', 'Cash'
        CARD = 'CARD', 'Card'
        UPI = 'UPI', 'UPI'
        BANK_TRANSFER = 'BANK_TRANSFER', 'Bank Transfer'
        ONLINE_GATEWAY = 'ONLINE_GATEWAY', 'Online Gateway'
        OTHER = 'OTHER', 'Other'

    class Status(models.TextChoices):
        PENDING = 'PENDING', 'Pending'
        SUCCESS = 'SUCCESS', 'Success'
        FAILED = 'FAILED', 'Failed'
        REFUNDED = 'REFUNDED', 'Refunded'          # fully refunded
        PARTIALLY_REFUNDED = 'PARTIALLY_REFUNDED', 'Partially Refunded'

    booking = models.ForeignKey(Booking, on_delete=models.CASCADE, related_name='payments')
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    method = models.CharField(max_length=20, choices=Method.choices, default=Method.CASH)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.SUCCESS)
    gateway_order_id = models.CharField(max_length=150, blank=True, db_index=True)
    transaction_reference = models.CharField(max_length=150, blank=True, db_index=True)
    gateway_response = models.JSONField(null=True, blank=True)
    paid_at = models.DateTimeField(null=True, blank=True)
    notes = models.CharField(max_length=255, blank=True)
    received_by = models.ForeignKey(
        'auth.User', on_delete=models.SET_NULL, null=True, blank=True, related_name='payments_received'
    )

    class Meta:
        db_table = 'payments'
        verbose_name = 'Payment'
        verbose_name_plural = 'Payments'
        ordering = ['-created_at']
        indexes = [models.Index(fields=['booking', 'status'])]

    def __str__(self):
        return f"{self.booking.booking_number} - {self.amount} ({self.status})"


class Invoice(BaseModel):
    """
    A generated bill for a Booking. Line items are stored as JSON
    (room charges, taxes, discounts) rather than a separate line-item
    model — invoices are a point-in-time snapshot of charges, not
    something that needs relational querying line-by-line.
    """
    booking = models.OneToOneField(Booking, on_delete=models.CASCADE, related_name='invoice')
    invoice_number = models.CharField(max_length=30, unique=True, db_index=True)
    line_items = models.JSONField(default=list)  # [{"description": "...", "amount": "..."}]
    subtotal = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    tax_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    discount_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    total_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    issued_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'invoices'
        verbose_name = 'Invoice'
        verbose_name_plural = 'Invoices'
        ordering = ['-issued_at']

    def __str__(self):
        return self.invoice_number


class Refund(BaseModel):
    """
    A refund against a specific Payment. Kept separate from Payment
    (rather than a negative-amount Payment row) since refunds have
    their own reason/status lifecycle and need clear audit separation
    from the original charge.
    """
    class Status(models.TextChoices):
        PENDING = 'PENDING', 'Pending'
        PROCESSED = 'PROCESSED', 'Processed'
        FAILED = 'FAILED', 'Failed'

    payment = models.ForeignKey(Payment, on_delete=models.CASCADE, related_name='refunds')
    booking = models.ForeignKey(Booking, on_delete=models.CASCADE, related_name='refunds')
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    reason = models.TextField(blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    transaction_reference = models.CharField(max_length=150, blank=True)
    processed_at = models.DateTimeField(null=True, blank=True)
    processed_by = models.ForeignKey(
        'auth.User', on_delete=models.SET_NULL, null=True, blank=True, related_name='refunds_processed'
    )

    class Meta:
        db_table = 'refunds'
        verbose_name = 'Refund'
        verbose_name_plural = 'Refunds'
        ordering = ['-created_at']

    def __str__(self):
        return f"Refund {self.amount} - {self.booking.booking_number}"