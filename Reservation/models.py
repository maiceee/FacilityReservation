from django.db import models
from django.contrib.auth.models import AbstractUser, UserManager as DjangoUserManager
from django.conf import settings


# =========================================================
# CUSTOM USER MANAGER
# =========================================================

class UserManager(DjangoUserManager):

    def create_superuser(
        self,
        username,
        email=None,
        password=None,
        **extra_fields
    ):
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        extra_fields.setdefault('role', 'ADMIN')

        return super().create_superuser(
            username,
            email,
            password,
            **extra_fields
        )


# =========================================================
# USER
# =========================================================

class User(AbstractUser):

    ROLE_CHOICES = [
        ('BASIC_USER', 'Basic User'),
        ('ADMIN', 'Admin'),
    ]

    role = models.CharField(
        max_length=10,
        choices=ROLE_CHOICES,
        default='BASIC_USER'
    )

    department = models.CharField(
        max_length=100,
        blank=True
    )

    contact_number = models.CharField(
        max_length=20,
        blank=True
    )

    objects = UserManager()

    def __str__(self):
        return self.username


# =========================================================
# FACILITY CATEGORY
# =========================================================

class FacilityCategory(models.Model):

    name = models.CharField(
        max_length=100,
        unique=True
    )

    is_active = models.BooleanField(
        default=True
    )

    def __str__(self):
        return self.name


# =========================================================
# AMENITY
# =========================================================

class Amenity(models.Model):

    name = models.CharField(
        max_length=100,
        unique=True
    )

    is_active = models.BooleanField(
        default=True
    )

    def __str__(self):
        return self.name


# =========================================================
# FACILITY
# =========================================================

class Facility(models.Model):

    facility_code = models.CharField(
        max_length=20,
        unique=True
    )

    name = models.CharField(
        max_length=100
    )

    category = models.ForeignKey(
        FacilityCategory,
        on_delete=models.PROTECT,
        related_name='facilities'
    )

    location = models.CharField(
        max_length=200
    )

    capacity = models.PositiveIntegerField()

    description = models.TextField(
        blank=True
    )

    opening_time = models.TimeField()

    closing_time = models.TimeField()

    is_active = models.BooleanField(
        default=True
    )

    def __str__(self):
        return f'{self.facility_code} - {self.name}'


# =========================================================
# FACILITY AMENITY
# =========================================================

class FacilityAmenity(models.Model):

    facility = models.ForeignKey(
        Facility,
        on_delete=models.CASCADE,
        related_name='facility_amenities'
    )

    amenity = models.ForeignKey(
        Amenity,
        on_delete=models.PROTECT,
        related_name='facility_amenities'
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['facility', 'amenity'],
                name='unique_facility_amenity'
            )
        ]

    def __str__(self):
        return f'{self.facility.name} - {self.amenity.name}'


# =========================================================
# RESERVATION
# =========================================================

class Reservation(models.Model):

    STATUS_CHOICES = [
        ('PENDING', 'Pending'),
        ('APPROVED', 'Approved'),
        ('REJECTED', 'Rejected'),
        ('CANCELLED', 'Cancelled'),
        ('CHECKED_IN', 'Checked In'),
        ('NO_SHOW', 'No Show'),
        ('COMPLETED', 'Completed'),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='reservations'
    )

    facility = models.ForeignKey(
        Facility,
        on_delete=models.PROTECT,
        related_name='reservations'
    )

    event_name = models.CharField(
        max_length=200
    )

    purpose = models.TextField()

    expected_attendees = models.PositiveIntegerField()

    start_datetime = models.DateTimeField()

    end_datetime = models.DateTimeField()

    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='PENDING'
    )

    decision_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='reservation_decisions'
    )

    decision_at = models.DateTimeField(
        null=True,
        blank=True
    )

    decision_reason = models.TextField(
        blank=True
    )

    created_at = models.DateTimeField(
        auto_now_add=True
    )

    updated_at = models.DateTimeField(
        auto_now=True
    )

    def __str__(self):
        return f'{self.event_name} - {self.status}'


# =========================================================
# CLOSURE BLOCK
# =========================================================

class ClosureBlock(models.Model):

    facility = models.ForeignKey(
        Facility,
        on_delete=models.PROTECT,
        related_name='closure_blocks'
    )

    start_datetime = models.DateTimeField()

    end_datetime = models.DateTimeField()

    reason = models.CharField(
        max_length=255
    )

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='created_closure_blocks'
    )

    is_active = models.BooleanField(
        default=True
    )

    created_at = models.DateTimeField(
        auto_now_add=True
    )

    archived_at = models.DateTimeField(
        null=True,
        blank=True
    )

    def __str__(self):
        return f'{self.facility.name} - {self.reason}'


# =========================================================
# RESERVATION CHANGE
# =========================================================

class ReservationChange(models.Model):

    reservation = models.ForeignKey(
        Reservation,
        on_delete=models.CASCADE,
        related_name='changes'
    )

    previous_start_datetime = models.DateTimeField()

    previous_end_datetime = models.DateTimeField()

    new_start_datetime = models.DateTimeField()

    new_end_datetime = models.DateTimeField()

    reason = models.TextField()

    changed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name='reservation_changes'
    )

    changed_at = models.DateTimeField(
        auto_now_add=True
    )

    def __str__(self):
        return f'Change - {self.reservation.event_name}'


# =========================================================
# EVENT RECORD
# =========================================================

class EventRecord(models.Model):

    reservation = models.OneToOneField(
        Reservation,
        on_delete=models.CASCADE,
        related_name='event_record'
    )

    checked_in_at = models.DateTimeField(
        null=True,
        blank=True
    )

    actual_start = models.DateTimeField(
        null=True,
        blank=True
    )

    actual_end = models.DateTimeField(
        null=True,
        blank=True
    )

    completed_at = models.DateTimeField(
        null=True,
        blank=True
    )

    no_show_at = models.DateTimeField(
        null=True,
        blank=True
    )

    incident_notes = models.TextField(
        blank=True
    )

    def __str__(self):
        return f'Event Record - {self.reservation.event_name}'


# =========================================================
# AUDIT LOG
# =========================================================

class AuditLog(models.Model):

    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='audit_logs'
    )

    action = models.CharField(
        max_length=100
    )

    reference = models.CharField(
        max_length=255,
        blank=True
    )

    description = models.TextField(
        blank=True
    )

    timestamp = models.DateTimeField(
        auto_now_add=True
    )

    def __str__(self):
        return f'{self.action} - {self.reference}'


# =========================================================
# SYSTEM SETTING
# =========================================================

class SystemSetting(models.Model):

    max_event_duration_hours = models.PositiveIntegerField(
        default=4
    )

    advance_booking_days = models.PositiveIntegerField(
        default=30
    )

    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='updated_system_settings'
    )

    updated_at = models.DateTimeField(
        auto_now=True
    )



    def __str__(self):
        return 'Booking Settings'