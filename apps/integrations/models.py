from django.db import models
from apps.core.models import BaseModel
from apps.properties.models import Property, RoomType, RatePlan


# class ChannelMapping(BaseModel):
   
#     property = models.ForeignKey(Property, on_delete=models.CASCADE, related_name='channel_mappings')
#     room_type = models.ForeignKey(RoomType, on_delete=models.CASCADE, null=True, blank=True, related_name='channel_mappings')
#     rate_plan = models.ForeignKey(RatePlan, on_delete=models.CASCADE, null=True, blank=True, related_name='channel_mappings')

#     staah_property_id = models.CharField(max_length=100, db_index=True)
#     staah_room_id = models.CharField(max_length=100, blank=True, db_index=True)
#     staah_rate_plan_id = models.CharField(max_length=100, blank=True, db_index=True)

#     class Meta:
#         db_table = 'channel_mappings'
#         verbose_name = 'Channel Mapping'
#         verbose_name_plural = 'Channel Mappings'
#         unique_together = [('property', 'room_type', 'rate_plan')]

#     def __str__(self):
#         return f"{self.property.code} -> STAAH:{self.staah_property_id}"

class ChannelMapping(BaseModel):
    class Provider(models.TextChoices):
        STAAH = 'STAAH', 'STAAH'
        CHANNEX = 'CHANNEX', 'Channex'

    provider = models.CharField(max_length=20, choices=Provider.choices, default=Provider.CHANNEX)
    property = models.ForeignKey(Property, on_delete=models.CASCADE, related_name='channel_mappings')
    room_type = models.ForeignKey(RoomType, on_delete=models.CASCADE, null=True, blank=True, related_name='channel_mappings')
    rate_plan = models.ForeignKey(RatePlan, on_delete=models.CASCADE, null=True, blank=True, related_name='channel_mappings')

    staah_property_id = models.CharField(max_length=100, blank=True, db_index=True)
    staah_room_id = models.CharField(max_length=100, blank=True, db_index=True)
    staah_rate_plan_id = models.CharField(max_length=100, blank=True, db_index=True)

    # Channex uses UUIDs for property_id, room_type_id, rate_plan_id
    channex_property_id = models.CharField(max_length=100, blank=True, db_index=True)
    channex_room_type_id = models.CharField(max_length=100, blank=True, db_index=True)
    channex_rate_plan_id = models.CharField(max_length=100, blank=True, db_index=True)

    class Meta:
        db_table = 'channel_mappings'
        verbose_name = 'Channel Mapping'
        verbose_name_plural = 'Channel Mappings'
        unique_together = [('provider', 'property', 'room_type', 'rate_plan')]

    def __str__(self):
        return f"{self.provider} - {self.property.code}"
        
class SyncLog(BaseModel):
    """
    Records every push/pull attempt to/from STAAH — success or failure.
    This is essential for debugging channel sync issues (e.g. "why didn't
    Booking.com show our updated rate?") without that, sync failures are
    invisible until a guest/OTA complains.
    """
    class SyncType(models.TextChoices):
        AVAILABILITY = 'AVAILABILITY', 'Availability'
        RATE = 'RATE', 'Rate'
        RESTRICTION = 'RESTRICTION', 'Restriction'
        RESERVATION_IN = 'RESERVATION_IN', 'Reservation (Incoming)'
        MODIFICATION_IN = 'MODIFICATION_IN', 'Modification (Incoming)'
        CANCELLATION_IN = 'CANCELLATION_IN', 'Cancellation (Incoming)'

    class Direction(models.TextChoices):
        OUTBOUND = 'OUTBOUND', 'Outbound (Push to STAAH)'
        INBOUND = 'INBOUND', 'Inbound (From STAAH)'

    class Status(models.TextChoices):
        PENDING = 'PENDING', 'Pending'
        SUCCESS = 'SUCCESS', 'Success'
        FAILED = 'FAILED', 'Failed'

    property = models.ForeignKey(Property, on_delete=models.CASCADE, related_name='sync_logs')
    sync_type = models.CharField(max_length=30, choices=SyncType.choices)
    direction = models.CharField(max_length=20, choices=Direction.choices)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    request_payload = models.JSONField(null=True, blank=True)
    response_payload = models.JSONField(null=True, blank=True)
    error_message = models.TextField(blank=True)

    class Meta:
        db_table = 'sync_logs'
        verbose_name = 'Sync Log'
        verbose_name_plural = 'Sync Logs'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['property', 'sync_type', 'status']),
            models.Index(fields=['created_at']),
        ]

    def __str__(self):
        return f"{self.sync_type} ({self.direction}) - {self.status} - {self.created_at:%Y-%m-%d %H:%M}"