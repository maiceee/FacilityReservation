"""Booking notifications share the originating save's transaction.

No message is emitted for an unchanged save or a rolled-back booking action.
Bulk queryset updates deliberately bypass model signals, as with Django saves.
"""
from django.db.models.signals import pre_save, post_save
from django.dispatch import receiver
from django.utils import timezone
from zoneinfo import ZoneInfo

from .models import Notification, PENDING_EXPIRY_REASON, Reservation, User


USER_COPY = {
    'expired': ('Your request was automatically cancelled', 'It was not approved before its start time. Submit a new request.'),
    'request': ('Request submitted', 'Awaiting administrator approval.'),
    'PENDING': ('Your request is pending', 'Awaiting administrator approval.'),
    'APPROVED': ('Your reservation is approved', 'View your reservation for details.'),
    'REJECTED': ('Your request was declined', 'Open your reservation to review the reason.'),
    'CANCELLED': ('Your reservation was cancelled', 'Submit a new request if your plans change.'),
    'CHECKED_IN': ('You’re checked in', 'View your reservation for details.'),
    'COMPLETED': ('Your event is complete', 'Your completion summary is available.'),
    'NO_SHOW': ('Your reservation was marked no-show', 'Open your reservation to review the record.'),
    'rescheduled': ('Your schedule has changed', 'Review your updated schedule.'),
}


def notification_copy(booking, event, *, for_admin):
    """Describe the saved event from the recipient's perspective, without guessing its actor."""
    start = timezone.localtime(booking.start_datetime, ZoneInfo('Asia/Manila'))
    end = timezone.localtime(booking.end_datetime, ZoneInfo('Asia/Manila'))
    end_format = '%I:%M %p' if start.date() == end.date() else '%b %d, %Y %I:%M %p'
    schedule = f'{start:%b %d, %Y %I:%M %p}–{end.strftime(end_format)} PHT'
    context = f'{booking.event_name[:100]} · {booking.facility.name} · #{booking.pk} · {schedule}'
    if for_admin:
        title = ('Request automatically cancelled' if event == 'expired' else
                 'New reservation request' if event == 'request' else
                 'Reservation rescheduled' if event == 'rescheduled' else
                 f'Reservation {booking.get_status_display().lower()}')
        requester = booking.user.get_full_name().strip() or booking.user.username
        reason = ' · Not approved before its start time.' if event == 'expired' else ''
        return title, f'{requester[:80]} · {context}{reason}'[:500]
    title, guidance = USER_COPY[event]
    return title, f'{context} · {guidance}'[:500]


@receiver(pre_save, sender=Reservation)
def remember_booking(sender, instance, raw=False, using='default', **kwargs):
    if raw:
        return
    instance._notification_before = (
        sender.objects.using(using).filter(pk=instance.pk)
        .values('status', 'start_datetime', 'end_datetime', 'facility_id').first()
        if instance.pk else None
    )


@receiver(post_save, sender=Reservation)
def notify_booking(sender, instance, created, raw=False, using='default', update_fields=None, **kwargs):
    if raw:
        return
    before = getattr(instance, '_notification_before', None)
    # Read persisted values: update_fields can intentionally leave dirty values unsaved.
    current = sender.objects.using(using).select_related('user', 'facility').get(pk=instance.pk)
    if created:
        event = 'request' if current.status == 'PENDING' else current.status
    elif before and before['status'] != current.status:
        event = 'expired' if (before['status'] == 'PENDING' and current.status == 'CANCELLED'
                              and current.decision_reason == PENDING_EXPIRY_REASON) else current.status
    elif before and any(before[field] != getattr(current, field)
                        for field in ('start_datetime', 'end_datetime', 'facility_id')):
        event = 'rescheduled'
    else:
        return
    recipients = set(User.objects.using(using).filter(role='ADMIN', is_active=True)
                     .values_list('pk', flat=True))
    recipients.add(current.user_id)
    notifications = []
    for recipient in recipients:
        # An administrator who owns the booking receives one personal update.
        title, message = notification_copy(current, event, for_admin=recipient != current.user_id)
        notifications.append(Notification(recipient_id=recipient, reservation=current,
                                          title=title, message=message))
    Notification.objects.using(using).bulk_create(notifications)
