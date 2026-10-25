"""Expire unapproved requests; conditional rechecks make repeated sweeps safe."""
import logging

from django.db import close_old_connections, transaction
from django.utils import timezone

from .models import AuditLog, PENDING_EXPIRY_REASON, Reservation

logger = logging.getLogger(__name__)


def expire_pending_reservations(*, now=None, user_id=None, reservation_id=None, batch_size=100):
    cutoff = now or timezone.now()
    due = Reservation.objects.filter(status='PENDING', start_datetime__lte=cutoff)
    if user_id is not None:
        due = due.filter(user_id=user_id)
    if reservation_id is not None:
        due = due.filter(pk=reservation_id)
    candidates = list(due.order_by('start_datetime', 'pk').values_list('pk', flat=True)[:batch_size])
    changed = 0
    for pk in candidates:
        with transaction.atomic():
            # Approval and concurrent sweeps must not overwrite one another.
            booking = Reservation.objects.select_for_update().filter(
                pk=pk, status='PENDING', start_datetime__lte=cutoff,
            ).first()
            if booking is None:
                continue
            booking.status = 'CANCELLED'
            booking.decision_by = None
            booking.decision_at = cutoff
            booking.decision_reason = PENDING_EXPIRY_REASON
            booking.save(update_fields=['status', 'decision_by', 'decision_at', 'decision_reason', 'updated_at'])
            AuditLog.objects.create(actor=None, action='RESERVATION_AUTO_CANCELLED',
                reference=f'Reservation #{pk}', description=PENDING_EXPIRY_REASON)
            changed += 1
    return changed


def run_expiry_worker(stop_event, interval=5):
    """Run beside the development server, or in a supervised management worker."""
    while not stop_event.is_set():
        count = 0
        try:
            close_old_connections()
            count = expire_pending_reservations()
            if count:
                logger.info('Automatically cancelled %s pending requests.', count)
        except Exception:
            logger.exception('Pending expiry sweep failed; it will retry.')
        finally:
            close_old_connections()
        if count >= 100:
            continue
        stop_event.wait(interval)
