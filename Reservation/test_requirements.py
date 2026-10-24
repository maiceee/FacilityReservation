import csv
import os
from datetime import datetime, time, timedelta
from io import StringIO
from unittest.mock import patch

from django.contrib.auth import SESSION_KEY
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from .forms import ReservationRequestForm, ReservationRescheduleForm
from .models import (
    AuditLog,
    ClosureBlock,
    EventRecord,
    Facility,
    FacilityCategory,
    Reservation,
    ReservationChange,
    SystemSetting,
    User,
)
from .services import (
    cancel_reservation,
    check_in_reservation,
    complete_reservation,
    create_reservation_request,
    mark_no_show,
    reschedule_reservation,
    validate_reservation_schedule,
)


def future_datetime(days=5, hour=10, minute=0):
    target_date = timezone.localdate() + timedelta(days=days)
    return timezone.make_aware(
        datetime.combine(target_date, time(hour, minute))
    )


class DemoSeedPasswordTest(TestCase):

    def test_seed_requires_password_outside_source_code(self):
        with patch.dict(
            os.environ,
            {'DEMO_ACCOUNT_PASSWORD': ''}
        ):
            with self.assertRaisesMessage(
                CommandError,
                'Provide the demo account password'
            ):
                call_command(
                    'seed_demo',
                    stdout=StringIO()
                )

        self.assertFalse(
            User.objects.filter(username='demo_admin').exists()
        )

    def test_seed_uses_environment_password(self):
        password = 'EnvironmentDemoPassword482!'

        with patch.dict(
            os.environ,
            {'DEMO_ACCOUNT_PASSWORD': password}
        ):
            call_command(
                'seed_demo',
                stdout=StringIO()
            )

        self.assertTrue(
            User.objects.get(username='demo_admin').check_password(password)
        )
        self.assertTrue(
            User.objects.get(
                username='demo_student01'
            ).check_password(password)
        )

    def test_command_option_overrides_environment_password(self):
        environment_password = 'EnvironmentDemoPassword482!'
        option_password = 'CommandOptionDemoPassword731!'

        with patch.dict(
            os.environ,
            {'DEMO_ACCOUNT_PASSWORD': environment_password}
        ):
            call_command(
                'seed_demo',
                password=option_password,
                stdout=StringIO()
            )

        demo_admin = User.objects.get(username='demo_admin')
        self.assertTrue(demo_admin.check_password(option_password))
        self.assertFalse(demo_admin.check_password(environment_password))


class RoleAndAccessRestrictionTest(TestCase):

    def setUp(self):
        self.admin = User.objects.create_user(
            username='accessadmin',
            password='TestPassword123!',
            role='ADMIN'
        )
        self.basic_user = User.objects.create_user(
            username='accessuser',
            password='TestPassword123!',
            role='BASIC_USER'
        )

    def test_anonymous_users_are_redirected_to_login(self):
        for url_name in ['admin_dashboard', 'user_dashboard']:
            with self.subTest(url_name=url_name):
                response = self.client.get(reverse(url_name))
                self.assertRedirects(response, reverse('login'))

    def test_basic_user_cannot_access_admin_routes(self):
        self.client.force_login(self.basic_user)

        for url_name in [
            'admin_dashboard',
            'user_management',
            'reservation_queue',
            'reports',
            'audit_logs',
        ]:
            with self.subTest(url_name=url_name):
                response = self.client.get(reverse(url_name))
                self.assertRedirects(response, reverse('user_dashboard'))

    def test_admin_cannot_access_basic_user_routes(self):
        self.client.force_login(self.admin)

        for url_name in [
            'user_dashboard',
            'user_profile',
            'browse_facilities',
            'my_reservations',
        ]:
            with self.subTest(url_name=url_name):
                response = self.client.get(reverse(url_name))
                self.assertRedirects(response, reverse('admin_dashboard'))

    def test_inactive_basic_user_session_is_terminated(self):
        self.basic_user.is_active = False
        self.basic_user.save(update_fields=['is_active'])
        self.client.force_login(self.basic_user)

        response = self.client.get(reverse('user_dashboard'))

        self.assertRedirects(response, reverse('login'))
        self.assertNotIn(SESSION_KEY, self.client.session)

    def test_inactive_admin_session_is_terminated(self):
        self.admin.is_active = False
        self.admin.save(update_fields=['is_active'])
        self.client.force_login(self.admin)

        response = self.client.get(reverse('admin_dashboard'))

        self.assertRedirects(response, reverse('login'))
        self.assertNotIn(SESSION_KEY, self.client.session)


class InactiveAccountLoginTest(TestCase):
    message = (
        'Your account has been deactivated. You are currently unable to '
        'log in. Please contact the system administrator for assistance '
        'or to request account reactivation.'
    )

    def setUp(self):
        self.password = 'TestPassword123!'
        self.inactive_user = User.objects.create_user(
            username='inactive-login-user',
            password=self.password,
            role='BASIC_USER',
            is_active=False,
        )

    def test_correct_credentials_show_deactivated_account_message(self):
        response = self.client.post(
            reverse('login'),
            {
                'username': self.inactive_user.username,
                'password': self.password,
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.message)
        self.assertNotIn(SESSION_KEY, self.client.session)

    def test_wrong_password_does_not_disclose_deactivated_status(self):
        response = self.client.post(
            reverse('login'),
            {
                'username': self.inactive_user.username,
                'password': 'WrongPassword123!',
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, self.message)
        self.assertContains(
            response,
            'Please enter a correct username and password.',
        )
        self.assertNotIn(SESSION_KEY, self.client.session)

    def test_active_account_can_still_log_in(self):
        active_user = User.objects.create_user(
            username='active-login-user',
            password=self.password,
            role='BASIC_USER',
        )

        response = self.client.post(
            reverse('login'),
            {
                'username': active_user.username,
                'password': self.password,
            },
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(
            int(self.client.session[SESSION_KEY]),
            active_user.pk,
        )


class AuthenticationHistoryProtectionTest(TestCase):
    def setUp(self):
        self.password = 'TestPassword123!'
        self.user = User.objects.create_user(
            username='history-protection-user',
            password=self.password,
            role='BASIC_USER',
        )

    def assert_response_is_not_cached(self, response):
        cache_control = response.headers.get('Cache-Control', '')
        self.assertIn('no-cache', cache_control)
        self.assertIn('no-store', cache_control)
        self.assertIn('must-revalidate', cache_control)

    def test_authenticated_pages_and_logout_are_not_cached(self):
        self.client.force_login(self.user)

        dashboard_response = self.client.get(reverse('user_dashboard'))
        self.assertEqual(dashboard_response.status_code, 200)
        self.assert_response_is_not_cached(dashboard_response)

        logout_response = self.client.post(reverse('logout'))
        self.assertRedirects(logout_response, reverse('login'))
        self.assert_response_is_not_cached(logout_response)
        self.assertNotIn(SESSION_KEY, self.client.session)

        previous_page_response = self.client.get(reverse('user_dashboard'))
        self.assertRedirects(previous_page_response, reverse('login'))

    def test_authenticated_user_cannot_reopen_login_page(self):
        login_response = self.client.get(reverse('login'))
        self.assert_response_is_not_cached(login_response)

        response = self.client.post(
            reverse('login'),
            {
                'username': self.user.username,
                'password': self.password,
            },
        )
        self.assertEqual(response.status_code, 302)

        previous_page_response = self.client.get(reverse('login'))
        self.assertRedirects(
            previous_page_response,
            reverse('dashboard_redirect'),
            fetch_redirect_response=False,
        )
        self.assert_response_is_not_cached(previous_page_response)


class RegistrationRoleTamperingTest(TestCase):

    def test_public_registration_cannot_create_an_admin(self):
        response = self.client.post(
            reverse('register'),
            {
                'username': 'tamperedregistration',
                'first_name': 'Taylor',
                'last_name': 'Cruz',
                'email': 'taylor.cruz@example.com',
                'department': 'Information Technology',
                'contact_number': '09171234567',
                'password1': 'SecurePassword123!',
                'password2': 'SecurePassword123!',
                'role': 'ADMIN',
                'is_staff': 'on',
                'is_superuser': 'on',
            }
        )

        self.assertRedirects(response, reverse('login'))
        account = User.objects.get(username='tamperedregistration')
        self.assertEqual(account.role, 'BASIC_USER')
        self.assertFalse(account.is_staff)
        self.assertFalse(account.is_superuser)


class ReservationOwnershipAndCancellationTest(TestCase):

    def setUp(self):
        self.owner = User.objects.create_user(
            username='reservationowner',
            password='TestPassword123!',
            role='BASIC_USER'
        )
        self.other_user = User.objects.create_user(
            username='otherreservationuser',
            password='TestPassword123!',
            role='BASIC_USER'
        )
        category = FacilityCategory.objects.create(
            name='Ownership Test Spaces',
            is_active=True
        )
        self.facility = Facility.objects.create(
            facility_code='OWN-101',
            name='Ownership Test Hall',
            category=category,
            location='Main Campus',
            capacity=50,
            opening_time=time(8),
            closing_time=time(18),
            is_active=True
        )
        start = future_datetime()
        self.owned_reservation = Reservation.objects.create(
            user=self.owner,
            facility=self.facility,
            event_name='Owner Event',
            purpose='Ownership test.',
            expected_attendees=20,
            start_datetime=start,
            end_datetime=start + timedelta(hours=1),
            status='PENDING'
        )
        self.other_reservation = Reservation.objects.create(
            user=self.other_user,
            facility=self.facility,
            event_name='Other User Event',
            purpose='Ownership test.',
            expected_attendees=20,
            start_datetime=start + timedelta(hours=2),
            end_datetime=start + timedelta(hours=3),
            status='PENDING'
        )
        self.client.force_login(self.owner)

    def test_reservation_list_contains_only_owned_records(self):
        response = self.client.get(reverse('my_reservations'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.owned_reservation.event_name)
        self.assertNotContains(response, self.other_reservation.event_name)

    def test_user_cannot_view_another_users_reservation(self):
        response = self.client.get(
            reverse(
                'reservation_detail_user',
                args=[self.other_reservation.pk]
            )
        )

        self.assertEqual(response.status_code, 404)

    def test_user_cannot_cancel_another_users_reservation(self):
        response = self.client.post(
            reverse(
                'reservation_cancel_user',
                args=[self.other_reservation.pk]
            )
        )

        self.assertEqual(response.status_code, 404)
        self.other_reservation.refresh_from_db()
        self.assertEqual(self.other_reservation.status, 'PENDING')

    def test_owner_can_cancel_pending_reservation_before_start(self):
        response = self.client.post(
            reverse(
                'reservation_cancel_user',
                args=[self.owned_reservation.pk]
            )
        )

        self.assertRedirects(
            response,
            reverse(
                'reservation_detail_user',
                args=[self.owned_reservation.pk]
            )
        )
        self.owned_reservation.refresh_from_db()
        self.assertEqual(self.owned_reservation.status, 'CANCELLED')
        self.assertTrue(
            AuditLog.objects.filter(
                actor=self.owner,
                action='RESERVATION_CANCELLED',
                reference=f'Reservation #{self.owned_reservation.pk}'
            ).exists()
        )

    def test_owner_cannot_cancel_after_reservation_start(self):
        self.owned_reservation.start_datetime = (
            timezone.now() - timedelta(hours=1)
        )
        self.owned_reservation.end_datetime = (
            timezone.now() + timedelta(hours=1)
        )
        self.owned_reservation.save(
            update_fields=['start_datetime', 'end_datetime', 'updated_at']
        )

        with self.assertRaisesMessage(
            ValidationError,
            'A reservation cannot be cancelled after its start time.'
        ):
            cancel_reservation(self.owned_reservation.pk, self.owner)

        self.owned_reservation.refresh_from_db()
        self.assertEqual(self.owned_reservation.status, 'PENDING')

    def test_owner_cannot_cancel_final_status(self):
        self.owned_reservation.status = 'COMPLETED'
        self.owned_reservation.save(update_fields=['status', 'updated_at'])

        with self.assertRaisesMessage(
            ValidationError,
            'This reservation can no longer be cancelled.'
        ):
            cancel_reservation(self.owned_reservation.pk, self.owner)

        self.owned_reservation.refresh_from_db()
        self.assertEqual(self.owned_reservation.status, 'COMPLETED')


class ReservationValidationRulesTest(TestCase):

    def setUp(self):
        self.user = User.objects.create_user(
            username='validationuser',
            password='TestPassword123!',
            role='BASIC_USER'
        )
        self.category = FacilityCategory.objects.create(
            name='Validation Test Spaces',
            is_active=True
        )
        self.facility = Facility.objects.create(
            facility_code='VAL-101',
            name='Validation Test Hall',
            category=self.category,
            location='Main Campus',
            capacity=30,
            opening_time=time(8),
            closing_time=time(18),
            is_active=True
        )
        SystemSetting.objects.create(
            max_event_duration_hours=4,
            advance_booking_days=30
        )
        self.start = future_datetime(days=5, hour=10)
        self.end = self.start + timedelta(hours=2)

    def validate(self, **overrides):
        values = {
            'facility': self.facility,
            'expected_attendees': 20,
            'start_datetime': self.start,
            'end_datetime': self.end,
        }
        values.update(overrides)
        return validate_reservation_schedule(**values)

    def test_capacity_and_active_facility_rules(self):
        with self.assertRaisesMessage(
            ValidationError,
            'capacity of 30'
        ):
            self.validate(expected_attendees=31)

        self.facility.is_active = False
        self.facility.save(update_fields=['is_active'])
        with self.assertRaisesMessage(
            ValidationError,
            'facility is currently inactive'
        ):
            self.validate()

        self.facility.is_active = True
        self.facility.save(update_fields=['is_active'])
        self.category.is_active = False
        self.category.save(update_fields=['is_active'])
        with self.assertRaisesMessage(
            ValidationError,
            'category of this facility is currently inactive'
        ):
            self.validate()

    def test_date_range_and_future_rules(self):
        with self.assertRaisesMessage(
            ValidationError,
            'End date and time must be later'
        ):
            self.validate(end_datetime=self.start)

        past_start = timezone.now() - timedelta(hours=2)
        with self.assertRaisesMessage(
            ValidationError,
            'start date and time must be in the future'
        ):
            self.validate(
                start_datetime=past_start,
                end_datetime=past_start + timedelta(hours=1)
            )

    def test_reservation_calendar_enforces_configured_date_window(self):
        local_now = timezone.make_aware(
            datetime(2026, 10, 20, 14, 35),
            timezone.get_current_timezone(),
        )

        with patch(
            'Reservation.forms.timezone.localtime',
            return_value=local_now,
        ):
            form = ReservationRequestForm()
            reschedule_form = ReservationRescheduleForm()

        expected_minimum = '2026-10-20T14:35'
        expected_maximum = '2026-11-19T23:59'
        self.assertEqual(
            form.fields['start_datetime'].widget.attrs['min'],
            expected_minimum,
        )
        self.assertEqual(
            form.fields['end_datetime'].widget.attrs['min'],
            expected_minimum,
        )
        self.assertEqual(
            form.fields['start_datetime'].widget.attrs['max'],
            expected_maximum,
        )
        self.assertEqual(
            form.fields['end_datetime'].widget.attrs['max'],
            expected_maximum,
        )
        self.assertEqual(
            reschedule_form.fields[
                'start_datetime'
            ].widget.attrs['max'],
            expected_maximum,
        )
        self.assertEqual(
            reschedule_form.fields[
                'end_datetime'
            ].widget.attrs['max'],
            expected_maximum,
        )

    def test_same_day_and_operating_hour_rules(self):
        early_start = future_datetime(days=5, hour=7)
        with self.assertRaisesMessage(
            ValidationError,
            'cannot start before 08:00 AM'
        ):
            self.validate(
                start_datetime=early_start,
                end_datetime=early_start + timedelta(hours=1)
            )

        late_start = future_datetime(days=5, hour=17)
        with self.assertRaisesMessage(
            ValidationError,
            'cannot end after 06:00 PM'
        ):
            self.validate(
                start_datetime=late_start,
                end_datetime=late_start + timedelta(hours=2)
            )

        overnight_start = future_datetime(days=5, hour=17)
        overnight_end = future_datetime(days=6, hour=9)
        with self.assertRaisesMessage(
            ValidationError,
            'Reservations cannot continue overnight.'
        ):
            self.validate(
                start_datetime=overnight_start,
                end_datetime=overnight_end
            )

    def test_duration_and_advance_booking_rules(self):
        with self.assertRaisesMessage(
            ValidationError,
            'maximum event duration is 4 hours'
        ):
            self.validate(end_datetime=self.start + timedelta(hours=5))

        too_far_start = future_datetime(days=31, hour=10)
        with self.assertRaisesMessage(
            ValidationError,
            'only be requested up to 30 calendar days in advance'
        ):
            self.validate(
                start_datetime=too_far_start,
                end_datetime=too_far_start + timedelta(hours=1)
            )

    def test_advance_window_includes_entire_final_calendar_date(self):
        local_now = timezone.make_aware(
            datetime(2026, 10, 20, 14, 35),
            timezone.get_current_timezone(),
        )
        final_date_start = timezone.make_aware(
            datetime(2026, 11, 19, 17, 0),
            timezone.get_current_timezone(),
        )
        following_date_start = timezone.make_aware(
            datetime(2026, 11, 20, 10, 0),
            timezone.get_current_timezone(),
        )

        with patch(
            'Reservation.services.timezone.now',
            return_value=local_now,
        ):
            self.assertTrue(
                self.validate(
                    start_datetime=final_date_start,
                    end_datetime=final_date_start + timedelta(hours=1),
                )
            )

            with self.assertRaisesMessage(
                ValidationError,
                'only be requested up to 30 calendar days in advance',
            ):
                self.validate(
                    start_datetime=following_date_start,
                    end_datetime=(
                        following_date_start + timedelta(hours=1)
                    ),
                )

    def test_active_closure_blocks_reservation_request(self):
        ClosureBlock.objects.create(
            facility=self.facility,
            start_datetime=self.start,
            end_datetime=self.end,
            reason='Maintenance.',
            created_by=self.user
        )

        with self.assertRaisesMessage(
            ValidationError,
            'because of a closure period'
        ):
            self.validate()

    def test_valid_request_is_created_as_pending_for_requesting_user(self):
        reservation = create_reservation_request(
            user=self.user,
            facility=self.facility,
            event_name='Valid Reservation',
            purpose='Validate a correct booking request.',
            expected_attendees=20,
            start_datetime=self.start,
            end_datetime=self.end
        )

        self.assertEqual(reservation.user, self.user)
        self.assertEqual(reservation.status, 'PENDING')


class ReschedulingRollbackTest(TestCase):

    def setUp(self):
        self.admin = User.objects.create_user(
            username='rollbackadmin',
            password='TestPassword123!',
            role='ADMIN'
        )
        self.user = User.objects.create_user(
            username='rollbackuser',
            password='TestPassword123!',
            role='BASIC_USER'
        )
        category = FacilityCategory.objects.create(
            name='Rollback Test Spaces',
            is_active=True
        )
        self.facility = Facility.objects.create(
            facility_code='RBK-101',
            name='Rollback Test Hall',
            category=category,
            location='Main Campus',
            capacity=50,
            opening_time=time(8),
            closing_time=time(18),
            is_active=True
        )
        original_start = future_datetime(days=4, hour=9)
        self.reservation = Reservation.objects.create(
            user=self.user,
            facility=self.facility,
            event_name='Original Event',
            purpose='Rollback validation.',
            expected_attendees=20,
            start_datetime=original_start,
            end_datetime=original_start + timedelta(hours=1),
            status='APPROVED'
        )
        self.original_start = self.reservation.start_datetime
        self.original_end = self.reservation.end_datetime
        self.conflict_start = future_datetime(days=5, hour=10)
        Reservation.objects.create(
            user=self.user,
            facility=self.facility,
            event_name='Blocking Event',
            purpose='Blocks the requested schedule.',
            expected_attendees=20,
            start_datetime=self.conflict_start,
            end_datetime=self.conflict_start + timedelta(hours=2),
            status='APPROVED'
        )

    def test_failed_reschedule_preserves_original_schedule_and_history(self):
        with self.assertRaisesMessage(
            ValidationError,
            'facility is already occupied'
        ):
            reschedule_reservation(
                reservation_id=self.reservation.pk,
                admin_user=self.admin,
                new_start_datetime=self.conflict_start,
                new_end_datetime=self.conflict_start + timedelta(hours=1),
                reason='Move into conflicting time.'
            )

        self.reservation.refresh_from_db()
        self.assertEqual(self.reservation.start_datetime, self.original_start)
        self.assertEqual(self.reservation.end_datetime, self.original_end)
        self.assertFalse(
            ReservationChange.objects.filter(
                reservation=self.reservation
            ).exists()
        )
        self.assertFalse(
            AuditLog.objects.filter(
                action='RESERVATION_RESCHEDULED',
                reference=f'Reservation #{self.reservation.pk}'
            ).exists()
        )


class EventStatusTransitionTest(TestCase):

    def setUp(self):
        self.admin = User.objects.create_user(
            username='eventadmin',
            password='TestPassword123!',
            role='ADMIN'
        )
        self.user = User.objects.create_user(
            username='eventuser',
            password='TestPassword123!',
            role='BASIC_USER'
        )
        category = FacilityCategory.objects.create(
            name='Event Test Spaces',
            is_active=True
        )
        self.facility = Facility.objects.create(
            facility_code='EVT-101',
            name='Event Test Hall',
            category=category,
            location='Main Campus',
            capacity=80,
            opening_time=time(8),
            closing_time=time(20),
            is_active=True
        )

    def create_reservation(self, status='APPROVED', ended=False):
        if ended:
            start = timezone.now() - timedelta(hours=2)
            end = timezone.now() - timedelta(hours=1)
        else:
            start = timezone.now() - timedelta(minutes=30)
            end = timezone.now() + timedelta(hours=1)

        return Reservation.objects.create(
            user=self.user,
            facility=self.facility,
            event_name=f'{status} Event',
            purpose='Event transition validation.',
            expected_attendees=30,
            start_datetime=start,
            end_datetime=end,
            status=status
        )

    def test_approved_event_can_be_checked_in_then_completed(self):
        reservation = self.create_reservation()

        check_in_reservation(reservation.pk, self.admin)
        reservation.refresh_from_db()
        event_record = EventRecord.objects.get(reservation=reservation)
        self.assertEqual(reservation.status, 'CHECKED_IN')
        self.assertIsNotNone(event_record.checked_in_at)
        self.assertIsNotNone(event_record.actual_start)

        complete_reservation(
            reservation.pk,
            self.admin,
            incident_notes='No incidents.'
        )
        reservation.refresh_from_db()
        event_record.refresh_from_db()
        self.assertEqual(reservation.status, 'COMPLETED')
        self.assertIsNotNone(event_record.actual_end)
        self.assertIsNotNone(event_record.completed_at)
        self.assertEqual(event_record.incident_notes, 'No incidents.')
        self.assertEqual(
            AuditLog.objects.filter(
                reference=f'Reservation #{reservation.pk}',
                action__in=[
                    'RESERVATION_CHECKED_IN',
                    'RESERVATION_COMPLETED',
                ]
            ).count(),
            2
        )

    def test_invalid_event_status_transitions_are_rejected(self):
        pending = self.create_reservation(status='PENDING')
        with self.assertRaisesMessage(
            ValidationError,
            'Only approved reservations can be checked in.'
        ):
            check_in_reservation(pending.pk, self.admin)

        approved = self.create_reservation(status='APPROVED')
        with self.assertRaisesMessage(
            ValidationError,
            'Only checked-in reservations can be completed.'
        ):
            complete_reservation(approved.pk, self.admin)

        future_approved = self.create_reservation(status='APPROVED')
        with self.assertRaisesMessage(
            ValidationError,
            'No-show can only be recorded after the scheduled end time.'
        ):
            mark_no_show(future_approved.pk, self.admin)

    def test_ended_approved_event_can_be_marked_no_show(self):
        reservation = self.create_reservation(ended=True)

        mark_no_show(reservation.pk, self.admin)

        reservation.refresh_from_db()
        event_record = EventRecord.objects.get(reservation=reservation)
        self.assertEqual(reservation.status, 'NO_SHOW')
        self.assertIsNotNone(event_record.no_show_at)
        self.assertTrue(
            AuditLog.objects.filter(
                actor=self.admin,
                action='RESERVATION_NO_SHOW',
                reference=f'Reservation #{reservation.pk}'
            ).exists()
        )


class ReportsAndReservationCsvTest(TestCase):

    def setUp(self):
        self.admin = User.objects.create_user(
            username='csvadmin',
            password='TestPassword123!',
            role='ADMIN'
        )
        self.basic_user = User.objects.create_user(
            username='csvuser',
            password='TestPassword123!',
            role='BASIC_USER'
        )
        category = FacilityCategory.objects.create(
            name='CSV Test Spaces',
            is_active=True
        )
        self.facility = Facility.objects.create(
            facility_code='CSV-101',
            name='CSV Test Hall',
            category=category,
            location='Main Campus',
            capacity=60,
            opening_time=time(8),
            closing_time=time(18),
            is_active=True
        )
        start = future_datetime(days=3, hour=10)
        self.reservation = Reservation.objects.create(
            user=self.basic_user,
            facility=self.facility,
            event_name='CSV Export Event',
            purpose='Report export validation.',
            expected_attendees=25,
            start_datetime=start,
            end_datetime=start + timedelta(hours=2),
            status='COMPLETED'
        )

    def test_report_totals_include_matching_reservations(self):
        self.client.force_login(self.admin)

        response = self.client.get(reverse('reports'))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['total_reservations'], 1)
        self.assertEqual(response.context['completed_reservations'], 1)
        self.assertEqual(response.context['total_booked_hours'], 2.0)

    def test_reservation_csv_contains_expected_header_and_row(self):
        self.client.force_login(self.admin)

        response = self.client.get(reverse('export_reservations_csv'))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'text/csv')
        self.assertIn(
            'reservation_report.csv',
            response['Content-Disposition']
        )
        rows = list(
            csv.reader(StringIO(response.content.decode('utf-8')))
        )
        self.assertEqual(
            rows[0],
            [
                'Reservation ID',
                'User',
                'Facility',
                'Event',
                'Participants',
                'Start',
                'End',
                'Status',
            ]
        )
        self.assertEqual(rows[1][1], self.basic_user.username)
        self.assertEqual(rows[1][2], self.facility.name)
        self.assertEqual(rows[1][3], self.reservation.event_name)
        self.assertEqual(rows[1][7], 'Completed')

    def test_basic_user_cannot_access_reports_or_csv_exports(self):
        self.client.force_login(self.basic_user)

        for url_name in [
            'reports',
            'export_reservations_csv',
            'export_facility_usage_csv',
        ]:
            with self.subTest(url_name=url_name):
                response = self.client.get(reverse(url_name))
                self.assertRedirects(response, reverse('user_dashboard'))
