from django.db import models
from apps.core.models import BaseModel


class Guest(BaseModel):
    """
    A person who has stayed or will stay at any property. Kept separate
    from Django's User model — guests don't log into this system, they're
    just records front desk creates/looks up when making a booking.
    One Guest can have many Bookings across different properties/visits.
    """
    first_name = models.CharField(max_length=100)
    last_name = models.CharField(max_length=100)
    email = models.EmailField(blank=True, db_index=True)
    phone = models.CharField(max_length=20, blank=True, db_index=True)
    id_proof_type = models.CharField(max_length=50, blank=True)  # Passport, Aadhaar, Driving License, etc.
    id_proof_number = models.CharField(max_length=100, blank=True)
    nationality = models.CharField(max_length=100, blank=True)
    address = models.CharField(max_length=500, blank=True)
    city = models.CharField(max_length=100, blank=True)
    country = models.CharField(max_length=100, blank=True)
    date_of_birth = models.DateField(null=True, blank=True)
    notes = models.TextField(blank=True)  # VIP preferences, allergies, special requests etc.

    class Meta:
        db_table = 'guests'
        verbose_name = 'Guest'
        verbose_name_plural = 'Guests'
        ordering = ['first_name', 'last_name']
        indexes = [
            models.Index(fields=['email']),
            models.Index(fields=['phone']),
        ]

    def __str__(self):
        return f"{self.first_name} {self.last_name}"

    @property
    def full_name(self):
        return f"{self.first_name} {self.last_name}"