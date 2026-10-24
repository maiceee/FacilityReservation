from datetime import timedelta

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from .models import (
    Reservation,
    Facility,
    ClosureBlock,
    ReservationChange,
    EventRecord,
    AuditLog,
    SystemSetting,
)


# =========================================================
# SYSTEM SETTINGS
# =========================================================

def get_system_settings():
    """
    Returns the single booking settings record.
    Creates the default settings when none exists.
    """
    settings_object = SystemSetting.objects.first()

    if settings_object is None:
        settings_object = SystemSetting.objects.create(
            max_event_duration_hours=4,
            advance_booking_days=30
        )

    return settings_object


# =========================================================
# AUDIT LOG
# =========================================================

def create_audit_log(
    actor,
    action,
    reference='',
    description=''
):
    return AuditLog.objects.create(
        actor=actor,
        action=action,
        reference=reference,
        description=description
    )


# =========================================================
# TIME OVERLAP
# =========================================================

def times_overlap(
    start_a,
    end_a,
    start_b,
    end_b
):
    """
    Half-open interval rule:

    [start, end)

    Two schedules conflict only when:

    startA < endB
    AND
    endA > startB

    Adjacent reservations are allowed.
    """

    return (
        start_a < end_b and
        end_a > start_b
    )


# =========================================================
# RESERVATION VALIDATION
# =========================================================

def validate_reservation_schedule(
    facility,
    expected_attendees,
    start_datetime,
    end_datetime,
    exclude_reservation=None
):
    """
    Performs the shared booking validation required by
    reservation requests, approvals and rescheduling.
    """

    errors = []

    if not facility.is_active:
        errors.append(
            'This facility is currently inactive.'
        )

    if not facility.category.is_active:
        errors.append(
            'The category of this facility is currently inactive.'
        )

    if expected_attendees < 1:
        errors.append(
            'Expected attendees must be at least 1.'
        )

    if expected_attendees > facility.capacity:
        errors.append(
            f'Expected attendees cannot exceed the facility '
            f'capacity of {facility.capacity}.'
        )

    if end_datetime <= start_datetime:
        errors.append(
            'End date and time must be later than start date and time.'
        )

    # Do not continue time calculations when the range is invalid.
    if end_datetime <= start_datetime:
        raise ValidationError(errors)

    now = timezone.now()

    if start_datetime <= now:
        errors.append(
            'The reservation start date and time must be in the future.'
        )

    # Reservation must stay within one calendar day.
    local_start = timezone.localtime(start_datetime)
    local_end = timezone.localtime(end_datetime)

    if local_start.date() != local_end.date():
        errors.append(
            'Reservations cannot continue overnight.'
        )

    # Facility operating hours.
    if local_start.time() < facility.opening_time:
        errors.append(
            f'The reservation cannot start before '
            f'{facility.opening_time.strftime("%I:%M %p")}.'
        )

    if local_end.time() > facility.closing_time:
        errors.append(
            f'The reservation cannot end after '
            f'{facility.closing_time.strftime("%I:%M %p")}.'
        )

    booking_settings = get_system_settings()

    duration = end_datetime - start_datetime

    maximum_duration = timedelta(
        hours=booking_settings.max_event_duration_hours
    )

    if duration > maximum_duration:
        errors.append(
            f'The maximum event duration is '
            f'{booking_settings.max_event_duration_hours} hours.'
        )

    latest_allowed_date = (
        timezone.localdate(now)
        + timedelta(days=booking_settings.advance_booking_days)
    )

    if local_start.date() > latest_allowed_date:
        errors.append(
            f'Reservations may only be requested up to '
            f'{booking_settings.advance_booking_days} calendar days '
            f'in advance.'
        )

    # -----------------------------------------------------
    # ACTIVE FACILITY CLOSURES
    # -----------------------------------------------------

    closure_conflict = ClosureBlock.objects.filter(
        facility=facility,
        is_active=True,
        start_datetime__lt=end_datetime,
        end_datetime__gt=start_datetime
    ).exists()

    if closure_conflict:
        errors.append(
            'The facility is unavailable during the selected schedule '
            'because of a closure period.'
        )

    # -----------------------------------------------------
    # RESERVATION CONFLICTS
    # -----------------------------------------------------

    blocking_reservations = Reservation.objects.filter(
        facility=facility,
        status__in=[
            'APPROVED',
            'CHECKED_IN',
            'COMPLETED',
            'NO_SHOW',
        ],
        start_datetime__lt=end_datetime,
        end_datetime__gt=start_datetime
    )

    if exclude_reservation is not None:
        blocking_reservations = blocking_reservations.exclude(
            pk=exclude_reservation.pk
        )

    if blocking_reservations.exists():
        errors.append(
            'The facility is already occupied during the selected schedule.'
        )

    if errors:
        raise ValidationError(errors)

    return True


# =========================================================
# CREATE RESERVATION REQUEST
# =========================================================

def create_reservation_request(
    user,
    facility,
    event_name,
    purpose,
    expected_attendees,
    start_datetime,
    end_datetime
):
    """
    Creates a Pending reservation.

    Pending reservations do NOT block the facility.
    """

    validate_reservation_schedule(
        facility=facility,
        expected_attendees=expected_attendees,
        start_datetime=start_datetime,
        end_datetime=end_datetime
    )

    reservation = Reservation.objects.create(
        user=user,
        facility=facility,
        event_name=event_name,
        purpose=purpose,
        expected_attendees=expected_attendees,
        start_datetime=start_datetime,
        end_datetime=end_datetime,
        status='PENDING'
    )

    return reservation


# =========================================================
# APPROVE RESERVATION
# =========================================================

@transaction.atomic
def approve_reservation(
    reservation_id,
    admin_user,
    reason
):
    """
    Approves a Pending reservation.

    The facility is locked before the final availability
    check so competing approval operations for the same
    facility are serialized on databases that support
    row-level locking.

    Availability is always revalidated inside the same
    transaction immediately before approval.
    """

    approval_reason = (reason or '').strip()

    if not approval_reason:
        raise ValidationError(
            'An approval reason is required.'
        )

    reservation = (
        Reservation.objects
        .select_for_update()
        .select_related(
            'facility',
            'facility__category',
            'user'
        )
        .get(pk=reservation_id)
    )

    if reservation.status != 'PENDING':
        raise ValidationError(
            'Only pending reservations can be approved.'
        )

    # -----------------------------------------------------
    # LOCK SHARED FACILITY
    #
    # Competing reservations may be different Reservation
    # rows, but they share the same Facility.
    # -----------------------------------------------------

    facility = (
        Facility.objects
        .select_for_update()
        .select_related('category')
        .get(pk=reservation.facility_id)
    )

    # -----------------------------------------------------
    # FINAL CONFLICT RECHECK
    #
    # This happens only after acquiring the shared
    # facility lock.
    # -----------------------------------------------------

    validate_reservation_schedule(
        facility=facility,
        expected_attendees=reservation.expected_attendees,
        start_datetime=reservation.start_datetime,
        end_datetime=reservation.end_datetime,
        exclude_reservation=reservation
    )

    reservation.status = 'APPROVED'
    reservation.decision_by = admin_user
    reservation.decision_at = timezone.now()
    reservation.decision_reason = approval_reason

    reservation.save(
        update_fields=[
            'status',
            'decision_by',
            'decision_at',
            'decision_reason',
            'updated_at',
        ]
    )

    create_audit_log(
        actor=admin_user,
        action='RESERVATION_APPROVED',
        reference=f'Reservation #{reservation.pk}',
        description=approval_reason
    )

    return reservation


# =========================================================
# REJECT RESERVATION
# =========================================================

@transaction.atomic
def reject_reservation(
    reservation_id,
    admin_user,
    reason
):
    reservation = (
        Reservation.objects
        .select_for_update()
        .get(pk=reservation_id)
    )

    if reservation.status != 'PENDING':
        raise ValidationError(
            'Only pending reservations can be rejected.'
        )

    if not reason or not reason.strip():
        raise ValidationError(
            'A rejection reason is required.'
        )

    reservation.status = 'REJECTED'
    reservation.decision_by = admin_user
    reservation.decision_at = timezone.now()
    reservation.decision_reason = reason.strip()

    reservation.save(
        update_fields=[
            'status',
            'decision_by',
            'decision_at',
            'decision_reason',
            'updated_at',
        ]
    )

    create_audit_log(
        actor=admin_user,
        action='RESERVATION_REJECTED',
        reference=f'Reservation #{reservation.pk}',
        description=reason.strip()
    )

    return reservation


# =========================================================
# CANCEL RESERVATION
# =========================================================

@transaction.atomic
def cancel_reservation(
    reservation_id,
    user
):
    """
    Basic User may cancel only their own Pending or
    Approved reservation before its scheduled start.
    """

    reservation = (
        Reservation.objects
        .select_for_update()
        .get(
            pk=reservation_id,
            user=user
        )
    )

    if reservation.status not in [
        'PENDING',
        'APPROVED',
    ]:
        raise ValidationError(
            'This reservation can no longer be cancelled.'
        )

    if timezone.now() >= reservation.start_datetime:
        raise ValidationError(
            'A reservation cannot be cancelled after its start time.'
        )

    reservation.status = 'CANCELLED'

    reservation.save(
        update_fields=[
            'status',
            'updated_at',
        ]
    )

    create_audit_log(
        actor=user,
        action='RESERVATION_CANCELLED',
        reference=f'Reservation #{reservation.pk}',
        description='Reservation cancelled by the owner.'
    )

    return reservation


# =========================================================
# ADMIN CANCEL APPROVED RESERVATION
# =========================================================

@transaction.atomic
def cancel_reservation_by_admin(
    reservation_id,
    admin_user,
    reason
):
    """
    Cancels an Approved reservation and records the
    administrator's required reason in the audit log.
    """

    reservation = (
        Reservation.objects
        .select_for_update()
        .get(pk=reservation_id)
    )

    if reservation.status != 'APPROVED':
        raise ValidationError(
            'Only an approved reservation can be cancelled.'
        )

    cancellation_reason = (reason or '').strip()

    if not cancellation_reason:
        raise ValidationError(
            'A cancellation reason is required.'
        )

    reservation.status = 'CANCELLED'
    reservation.save(
        update_fields=[
            'status',
            'updated_at',
        ]
    )

    create_audit_log(
        actor=admin_user,
        action='RESERVATION_CANCELLED',
        reference=f'Reservation #{reservation.pk}',
        description=cancellation_reason
    )

    return reservation


# =========================================================
# RESCHEDULE APPROVED RESERVATION
# =========================================================

@transaction.atomic
def reschedule_reservation(
    reservation_id,
    admin_user,
    new_start_datetime,
    new_end_datetime,
    reason
):
    """
    Reschedules an Approved reservation.

    The facility is locked before validating the new
    schedule. If validation fails, the transaction is
    rolled back and the original schedule remains intact.
    """

    reservation = (
        Reservation.objects
        .select_for_update()
        .select_related(
            'facility',
            'facility__category'
        )
        .get(pk=reservation_id)
    )

    if reservation.status != 'APPROVED':
        raise ValidationError(
            'Only approved reservations can be rescheduled.'
        )

    if not reason or not reason.strip():
        raise ValidationError(
            'A rescheduling reason is required.'
        )

    # -----------------------------------------------------
    # LOCK SHARED FACILITY
    # -----------------------------------------------------

    facility = (
        Facility.objects
        .select_for_update()
        .select_related('category')
        .get(pk=reservation.facility_id)
    )

    # -----------------------------------------------------
    # VALIDATE NEW SCHEDULE BEFORE CHANGING ORIGINAL
    # -----------------------------------------------------

    validate_reservation_schedule(
        facility=facility,
        expected_attendees=reservation.expected_attendees,
        start_datetime=new_start_datetime,
        end_datetime=new_end_datetime,
        exclude_reservation=reservation
    )

    previous_start = reservation.start_datetime
    previous_end = reservation.end_datetime

    # -----------------------------------------------------
    # SAVE RESCHEDULING HISTORY
    # -----------------------------------------------------

    ReservationChange.objects.create(
        reservation=reservation,
        previous_start_datetime=previous_start,
        previous_end_datetime=previous_end,
        new_start_datetime=new_start_datetime,
        new_end_datetime=new_end_datetime,
        reason=reason.strip(),
        changed_by=admin_user
    )

    # -----------------------------------------------------
    # APPLY NEW SCHEDULE
    # -----------------------------------------------------

    reservation.start_datetime = new_start_datetime
    reservation.end_datetime = new_end_datetime

    reservation.save(
        update_fields=[
            'start_datetime',
            'end_datetime',
            'updated_at',
        ]
    )

    create_audit_log(
        actor=admin_user,
        action='RESERVATION_RESCHEDULED',
        reference=f'Reservation #{reservation.pk}',
        description=reason.strip()
    )

    return reservation


# =========================================================
# ARCHIVE FACILITY CLOSURE
# =========================================================

@transaction.atomic
def archive_closure_block(
    closure_id,
    admin_user
):
    """
    Archives only an unused closure block.

    A closure is no longer considered unused once its scheduled period has
    started or when any reservation record overlaps the closure period.
    """

    closure = (
        ClosureBlock.objects
        .select_for_update()
        .select_related('facility')
        .get(pk=closure_id)
    )

    if not closure.is_active:
        raise ValidationError(
            'This closure has already been archived.'
        )

    if closure.start_datetime <= timezone.now():
        raise ValidationError(
            'Only unused future closures can be archived. '
            'This closure has already started.'
        )

    has_overlapping_reservation = Reservation.objects.filter(
        facility_id=closure.facility_id,
        start_datetime__lt=closure.end_datetime,
        end_datetime__gt=closure.start_datetime
    ).exists()

    if has_overlapping_reservation:
        raise ValidationError(
            'Only unused closures can be archived. A reservation '
            'overlaps this closure period.'
        )

    closure.is_active = False
    closure.archived_at = timezone.now()
    closure.save(
        update_fields=[
            'is_active',
            'archived_at',
        ]
    )

    create_audit_log(
        actor=admin_user,
        action='CLOSURE_ARCHIVED',
        reference=f'Closure #{closure.pk}',
        description=closure.reason
    )

    return closure


# =========================================================
# CHECK IN
# =========================================================

@transaction.atomic
def check_in_reservation(
    reservation_id,
    admin_user
):
    reservation = (
        Reservation.objects
        .select_for_update()
        .get(pk=reservation_id)
    )

    if reservation.status != 'APPROVED':
        raise ValidationError(
            'Only approved reservations can be checked in.'
        )

    current_time = timezone.now()

    event_record, created = EventRecord.objects.get_or_create(
        reservation=reservation
    )

    if event_record.checked_in_at is not None:
        raise ValidationError(
            'This reservation has already been checked in.'
        )

    event_record.checked_in_at = current_time
    event_record.actual_start = current_time

    event_record.save(
        update_fields=[
            'checked_in_at',
            'actual_start',
        ]
    )

    reservation.status = 'CHECKED_IN'

    reservation.save(
        update_fields=[
            'status',
            'updated_at',
        ]
    )

    create_audit_log(
        actor=admin_user,
        action='RESERVATION_CHECKED_IN',
        reference=f'Reservation #{reservation.pk}',
        description='Event checked in.'
    )

    return reservation


# =========================================================
# COMPLETE EVENT
# =========================================================

@transaction.atomic
def complete_reservation(
    reservation_id,
    admin_user,
    incident_notes=''
):
    reservation = (
        Reservation.objects
        .select_for_update()
        .get(pk=reservation_id)
    )

    if reservation.status != 'CHECKED_IN':
        raise ValidationError(
            'Only checked-in reservations can be completed.'
        )

    event_record = EventRecord.objects.filter(
        reservation=reservation
    ).first()

    if event_record is None or event_record.checked_in_at is None:
        raise ValidationError(
            'The event must be checked in before completion.'
        )

    current_time = timezone.now()

    actual_start = (
        event_record.actual_start
        or event_record.checked_in_at
    )

    if current_time < actual_start:
        raise ValidationError(
            'Actual end cannot be earlier than actual start.'
        )

    event_record.actual_end = current_time
    event_record.completed_at = current_time
    event_record.incident_notes = incident_notes.strip()

    event_record.save(
        update_fields=[
            'actual_end',
            'completed_at',
            'incident_notes',
        ]
    )

    reservation.status = 'COMPLETED'

    reservation.save(
        update_fields=[
            'status',
            'updated_at',
        ]
    )

    create_audit_log(
        actor=admin_user,
        action='RESERVATION_COMPLETED',
        reference=f'Reservation #{reservation.pk}',
        description='Event marked as completed.'
    )

    return reservation


# =========================================================
# NO SHOW
# =========================================================

@transaction.atomic
def mark_no_show(
    reservation_id,
    admin_user
):
    reservation = (
        Reservation.objects
        .select_for_update()
        .get(pk=reservation_id)
    )

    if reservation.status != 'APPROVED':
        raise ValidationError(
            'Only approved reservations can be marked as no-show.'
        )

    if timezone.now() < reservation.end_datetime:
        raise ValidationError(
            'No-show can only be recorded after the scheduled end time.'
        )

    event_record, created = EventRecord.objects.get_or_create(
        reservation=reservation
    )

    if event_record.checked_in_at is not None:
        raise ValidationError(
            'A checked-in reservation cannot be marked as no-show.'
        )

    event_record.no_show_at = timezone.now()

    event_record.save(
        update_fields=[
            'no_show_at',
        ]
    )

    reservation.status = 'NO_SHOW'

    reservation.save(
        update_fields=[
            'status',
            'updated_at',
        ]
    )

    create_audit_log(
        actor=admin_user,
        action='RESERVATION_NO_SHOW',
        reference=f'Reservation #{reservation.pk}',
        description='Reservation marked as no-show.'
    )

    return reservation
