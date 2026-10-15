from django.db import models
from apps.core.models import TimeStampedModel


class Inquiry(TimeStampedModel):
    """A message submitted through the website's enquiry form."""

    class Status(models.TextChoices):
        NEW = 'NEW', 'New'
        CONTACTED = 'CONTACTED', 'Contacted'
        CLOSED = 'CLOSED', 'Closed'

    name = models.CharField(max_length=100)
    email = models.EmailField()
    phone = models.CharField(max_length=20)
    hotel = models.CharField(max_length=100)
    comment = models.TextField()

    status = models.CharField(max_length=20, choices=Status.choices, default=Status.NEW, db_index=True)
    admin_notes = models.TextField(blank=True)

    source_page = models.CharField(max_length=200, blank=True)   # landing page or contact page
    ip_address = models.GenericIPAddressField(null=True, blank=True)

    class Meta:
        db_table = 'inquiries'
        verbose_name = 'Inquiry'
        verbose_name_plural = 'Inquiries'
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.name} - {self.hotel} ({self.created_at:%Y-%m-%d})"