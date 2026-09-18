import uuid
from django.conf import settings
from django.db import models


class TimeStampedModel(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class UUIDModel(models.Model):
    uuid = models.UUIDField(default=uuid.uuid4, editable=False, unique=True, db_index=True)

    class Meta:
        abstract = True


class BaseModel(TimeStampedModel):
    is_active = models.BooleanField(default=True)

    class Meta:
        abstract = True


class Module(models.TextChoices):
    PROPERTIES = 'PROPERTIES', 'Properties'
    ROOM_TYPES = 'ROOM_TYPES', 'Room Types'
    ROOMS = 'ROOMS', 'Rooms'
    RATE_PLANS = 'RATE_PLANS', 'Rate Plans'
    AVAILABILITY = 'AVAILABILITY', 'Availability'
    GUESTS = 'GUESTS', 'Guests'
    BOOKINGS = 'BOOKINGS', 'Bookings'
    PAYMENTS = 'PAYMENTS', 'Payments'
    REPORTS = 'REPORTS', 'Reports'
    STAFF = 'STAFF', 'Staff & Permissions'
    INTEGRATIONS = 'INTEGRATIONS', 'STAAH Integration'


class StaffProfile(TimeStampedModel):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='staff_profile'
    )
    employee_code = models.CharField(max_length=30, unique=True, blank=True, null=True)
    phone = models.CharField(max_length=20, blank=True)
    property = models.ForeignKey(
        'properties.Property', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='staff_members'
    )
    is_active = models.BooleanField(default=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='staff_created'
    )

    class Meta:
        db_table = 'staff_profiles'
        verbose_name = 'Staff Profile'
        verbose_name_plural = 'Staff Profiles'

    def __str__(self):
        return f"{self.user.get_full_name() or self.user.username}"

    def has_permission(self, module, action='view'):
        if self.user.is_superuser:
            return True
        perm = self.permissions.filter(module=module).first()
        if not perm:
            return False
        return getattr(perm, f'can_{action}', False)


class StaffPermission(TimeStampedModel):
    staff = models.ForeignKey(
        StaffProfile, on_delete=models.CASCADE, related_name='permissions'
    )
    module = models.CharField(max_length=30, choices=Module.choices)
    can_view = models.BooleanField(default=False)
    can_add = models.BooleanField(default=False)
    can_edit = models.BooleanField(default=False)
    can_delete = models.BooleanField(default=False)

    class Meta:
        db_table = 'staff_permissions'
        verbose_name = 'Staff Permission'
        verbose_name_plural = 'Staff Permissions'
        unique_together = [('staff', 'module')]

    def __str__(self):
        return f"{self.staff} - {self.get_module_display()}"