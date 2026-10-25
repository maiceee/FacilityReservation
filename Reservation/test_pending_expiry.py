from datetime import time, timedelta
from io import StringIO
from unittest.mock import Mock, patch

from django.core.exceptions import ValidationError
from django.core.management import call_command, get_commands
from django.db import OperationalError, transaction
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from .expiry import expire_pending_reservations
from .models import AuditLog, Facility, FacilityCategory, Notification, PENDING_EXPIRY_REASON, Reservation, User
from .services import approve_reservation, reject_reservation


class PendingExpiryTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username='expiry-user')
        cls.other = User.objects.create_user(username='expiry-other')
        cls.admin = User.objects.create_user(username='expiry-admin', role='ADMIN')
        category = FacilityCategory.objects.create(name='Expiry rooms')
        cls.facility = Facility.objects.create(facility_code='EXP-1', name='Meeting room',
            category=category, location='Campus', capacity=20, opening_time=time(8), closing_time=time(20))

    def setUp(self):
        self.now = timezone.now().replace(microsecond=0)

    def booking(self, minutes, status='PENDING', user=None):
        return Reservation.objects.bulk_create([Reservation(user=user or self.user, facility=self.facility,
            event_name='Expiry test', purpose='Study', expected_attendees=5, status=status,
            start_datetime=self.now+timedelta(minutes=minutes), end_datetime=self.now+timedelta(minutes=minutes+60))])[0]

    def test_exact_start_cancels_only_pending_with_reason_audit_and_both_role_notifications(self):
        due = self.booking(0)
        future = self.booking(1)
        approved = self.booking(-10, 'APPROVED')
        checked = self.booking(-10, 'CHECKED_IN')
        self.assertEqual(expire_pending_reservations(now=self.now), 1)
        due.refresh_from_db()
        self.assertEqual(due.status, 'CANCELLED')
        self.assertEqual(due.decision_reason, PENDING_EXPIRY_REASON)
        self.assertIsNone(due.decision_by)
        self.assertEqual(due.decision_at, self.now)
        self.assertTrue(due.auto_cancelled)
        for booking, status in ((future, 'PENDING'), (approved, 'APPROVED'), (checked, 'CHECKED_IN')):
            booking.refresh_from_db()
            self.assertEqual(booking.status, status)
        audit = AuditLog.objects.get(action='RESERVATION_AUTO_CANCELLED')
        self.assertIsNone(audit.actor)
        self.assertEqual(Notification.objects.filter(reservation=due).count(), 2)
        self.assertEqual(Notification.objects.get(recipient=self.user).title, 'Your request was automatically cancelled')
        self.assertEqual(Notification.objects.get(recipient=self.admin).title, 'Request automatically cancelled')

    def test_repeated_sweep_does_not_duplicate_events_or_change_terminal_records(self):
        self.booking(-60)
        for status in ('REJECTED', 'CANCELLED', 'COMPLETED', 'NO_SHOW'):
            self.booking(-60, status)
        self.assertEqual(expire_pending_reservations(now=self.now), 1)
        self.assertEqual(expire_pending_reservations(now=self.now), 0)
        self.assertEqual(AuditLog.objects.count(), 1)
        self.assertEqual(Notification.objects.count(), 2)

    def test_cancel_audit_and_notifications_roll_back_together(self):
        booking = self.booking(-1)
        with self.assertRaises(ValueError):
            with transaction.atomic():
                expire_pending_reservations(now=self.now)
                raise ValueError('rollback')
        booking.refresh_from_db()
        self.assertEqual(booking.status, 'PENDING')
        self.assertFalse(AuditLog.objects.exists())
        self.assertFalse(Notification.objects.exists())

    def test_late_approval_cannot_revive_the_request_or_rollback_expiry(self):
        booking = self.booking(-1)
        with self.assertRaisesMessage(ValidationError, 'automatically cancelled'):
            approve_reservation(booking.pk, self.admin, 'Late approval')
        booking.refresh_from_db()
        self.assertEqual(booking.status, 'CANCELLED')
        self.assertEqual(Notification.objects.count(), 2)
        with self.assertRaisesMessage(ValidationError, 'automatically cancelled'):
            reject_reservation(booking.pk, self.admin, 'Late rejection')
        self.assertEqual(Notification.objects.count(), 2)

    def test_authenticated_pages_expire_owned_requests_and_remove_review_controls(self):
        booking = self.booking(-1)
        foreign = self.booking(-1, user=self.other)
        self.client.force_login(self.user)
        response = self.client.get(reverse('my_reservations'))
        booking.refresh_from_db()
        foreign.refresh_from_db()
        self.assertEqual(booking.status, 'CANCELLED')
        self.assertEqual(foreign.status, 'PENDING')
        self.assertContains(response, 'Not approved before start')
        detail = self.client.get(reverse('reservation_detail_user', args=[booking.pk]))
        self.assertContains(detail, 'Automatically cancelled because')
        self.assertNotContains(detail, 'Administrator decision')
        self.client.force_login(self.admin)
        admin = self.client.get(reverse('reservation_detail_admin', args=[booking.pk]))
        self.assertNotContains(admin, 'Approve Reservation')
        self.assertNotContains(admin, 'Reject Reservation')
        self.assertContains(admin, PENDING_EXPIRY_REASON)
        self.assertContains(admin, 'System')

    def test_command_dry_run_does_not_write_and_runserver_uses_automatic_worker(self):
        booking = self.booking(-1)
        output = StringIO()
        call_command('expire_pending_reservations', dry_run=True, stdout=output)
        self.assertIn('1 pending requests are due', output.getvalue())
        booking.refresh_from_db()
        self.assertEqual(booking.status, 'PENDING')
        call_command('expire_pending_reservations', stdout=StringIO())
        booking.refresh_from_db()
        self.assertEqual(booking.status, 'CANCELLED')
        self.assertEqual(get_commands()['runserver'], 'Reservation')

    def test_specific_detail_is_fresh_even_when_due_backlog_exceeds_one_batch(self):
        for _ in range(101):
            self.booking(-10)
        last = self.booking(-1)
        self.client.force_login(self.admin)
        response = self.client.get(reverse('reservation_detail_admin', args=[last.pk]))
        last.refresh_from_db()
        self.assertEqual(last.status, 'CANCELLED')
        self.assertNotContains(response, 'Approve Reservation')

    def test_background_worker_retries_after_a_database_error(self):
        from .expiry import run_expiry_worker
        stop = Mock()
        stop.is_set.side_effect = [False, False, True]
        with patch('Reservation.expiry.close_old_connections'), patch(
                'Reservation.expiry.expire_pending_reservations', side_effect=[OperationalError('busy'), 1]) as sweep:
            with self.assertLogs('Reservation.expiry', level='ERROR'):
                run_expiry_worker(stop)
        self.assertEqual(sweep.call_count, 2)
