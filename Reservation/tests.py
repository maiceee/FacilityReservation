import csv
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from io import StringIO
from threading import Barrier

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import close_old_connections
from django.test import SimpleTestCase, TestCase, TransactionTestCase
from django.urls import reverse
from django.utils import timezone

from .models import (
    AuditLog,
    ClosureBlock,
    User,
    FacilityCategory,
    Facility,
    Reservation,
    SystemSetting,
)
from .services import (
    approve_reservation,
    archive_closure_block,
    reschedule_reservation,
)


class DjangoConfigurationTest(SimpleTestCase):

    def test_project_uses_manila_timezone(self):
        self.assertEqual(settings.TIME_ZONE, 'Asia/Manila')
        self.assertTrue(settings.USE_TZ)
        self.assertEqual(
            timezone.get_default_timezone_name(),
            'Asia/Manila'
        )

    def test_django_admin_application_is_disabled(self):
        self.assertNotIn(
            'django.contrib.admin',
            settings.INSTALLED_APPS
        )

    def test_django_admin_url_is_not_exposed(self):
        response = self.client.get('/admin/')

        self.assertEqual(response.status_code, 404)


class CustomAdministrationInterfaceTest(TestCase):

    def test_administrator_uses_custom_dashboard(self):
        administrator = User.objects.create_user(
            username='customadmin',
            password='TestPassword123!',
            role='ADMIN'
        )
        self.client.force_login(administrator)

        response = self.client.get(reverse('admin_dashboard'))

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(
            response,
            'Reservation/admin/dashboard/AdminDashboard.html'
        )

    def test_user_details_page_has_no_character_before_document(self):
        administrator = User.objects.create_user(
            username='userdetailadmin',
            password='TestPassword123!',
            role='ADMIN'
        )
        account = User.objects.create_user(
            username='userdetailaccount',
            password='TestPassword123!',
            role='BASIC_USER'
        )
        self.client.force_login(administrator)

        response = self.client.get(
            reverse('admin_user_detail', args=[account.pk])
        )

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(
            response,
            'Reservation/admin/users/UserDetail.html'
        )
        self.assertTrue(
            response.content.lstrip().startswith(b'<!DOCTYPE html>')
        )


class RegistrationAndProfileAuditTest(TestCase):

    def setUp(self):
        self.user = User.objects.create_user(
            username='profileaudituser',
            password='TestPassword123!',
            role='BASIC_USER',
            first_name='Jordan',
            last_name='Reyes',
            email='jordan@example.com',
            department='Information Technology',
            contact_number='09170000000'
        )

    def test_successful_registration_creates_audit_record(self):
        response = self.client.post(
            reverse('register'),
            {
                'username': 'newaudituser',
                'first_name': 'Alex',
                'last_name': 'Santos',
                'email': 'alex.santos@example.com',
                'department': 'Engineering',
                'contact_number': '09171112222',
                'password1': 'SecurePassword123!',
                'password2': 'SecurePassword123!',
            }
        )

        self.assertRedirects(response, reverse('login'))
        account = User.objects.get(username='newaudituser')
        audit = AuditLog.objects.get(
            action='ACCOUNT_REGISTERED',
            reference=f'User #{account.pk}'
        )
        self.assertEqual(account.role, 'BASIC_USER')
        self.assertEqual(audit.actor, account)
        self.assertIn(account.username, audit.description)

    def test_invalid_registration_does_not_create_audit_record(self):
        response = self.client.post(
            reverse('register'),
            {
                'username': 'invalidaudituser',
                'first_name': 'Invalid',
                'last_name': 'Account',
                'email': self.user.email,
                'department': 'Engineering',
                'contact_number': '09173334444',
                'password1': 'SecurePassword123!',
                'password2': 'SecurePassword123!',
            }
        )

        self.assertEqual(response.status_code, 200)
        self.assertFalse(
            User.objects.filter(username='invalidaudituser').exists()
        )
        self.assertFalse(
            AuditLog.objects.filter(action='ACCOUNT_REGISTERED').exists()
        )

    def test_profile_update_creates_audit_record(self):
        self.client.force_login(self.user)

        response = self.client.post(
            reverse('user_profile'),
            {
                'first_name': 'Jordana',
                'last_name': self.user.last_name,
                'contact_number': '09179998888',
            }
        )

        self.assertRedirects(response, reverse('user_profile'))
        self.user.refresh_from_db()
        audit = AuditLog.objects.get(
            action='PROFILE_UPDATED',
            reference=f'User #{self.user.pk}'
        )
        self.assertEqual(self.user.first_name, 'Jordana')
        self.assertEqual(self.user.contact_number, '09179998888')
        self.assertEqual(audit.actor, self.user)
        self.assertIn('First name', audit.description)
        self.assertIn('Contact number', audit.description)
        self.assertNotIn('09179998888', audit.description)

    def test_unchanged_profile_does_not_create_audit_record(self):
        self.client.force_login(self.user)

        response = self.client.post(
            reverse('user_profile'),
            {
                'first_name': self.user.first_name,
                'last_name': self.user.last_name,
                'contact_number': self.user.contact_number,
            }
        )

        self.assertRedirects(response, reverse('user_profile'))
        self.assertFalse(
            AuditLog.objects.filter(action='PROFILE_UPDATED').exists()
        )


class FacilityAvailabilityWindowTest(TestCase):

    def setUp(self):
        self.user = User.objects.create_user(
            username='availabilityuser',
            password='TestPassword123!',
            role='BASIC_USER'
        )
        self.category = FacilityCategory.objects.create(
            name='Availability Test Spaces',
            is_active=True
        )
        self.facility = Facility.objects.create(
            facility_code='AVL-101',
            name='Availability Test Hall',
            category=self.category,
            location='Main Campus',
            capacity=40,
            opening_time='00:00',
            closing_time='23:59',
            is_active=True
        )
        SystemSetting.objects.create(
            max_event_duration_hours=4,
            advance_booking_days=12
        )
        self.client.force_login(self.user)

    def test_availability_uses_configured_advance_booking_window(self):
        response = self.client.get(
            reverse(
                'facility_detail_user',
                args=[self.facility.pk]
            )
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['availability_days'], 12)
        available_dates = {
            slot['date']
            for slot in response.context['available_slots']
        }
        self.assertEqual(len(available_dates), 12)
        self.assertContains(
            response,
            'Available time periods for the next'
        )
        self.assertContains(response, '12 days')
        self.assertNotContains(response, 'next 7 days')


class FacilityManagementTest(TestCase):

    def setUp(self):
        self.admin = User.objects.create_user(
            username='facilityadmin',
            password='TestPassword123!',
            role='ADMIN'
        )
        self.category = FacilityCategory.objects.create(
            name='Learning Spaces',
            is_active=True
        )
        self.facility = Facility.objects.create(
            facility_code='LIB-201',
            name='Library Collaboration Room',
            category=self.category,
            location='Main Library, Second Floor',
            capacity=24,
            description='A collaborative learning space.',
            opening_time='08:00',
            closing_time='18:00',
            is_active=True
        )
        self.other_facility = Facility.objects.create(
            facility_code='GYM-001',
            name='University Gymnasium',
            category=self.category,
            location='Athletics Complex',
            capacity=300,
            description='The main indoor athletics venue.',
            opening_time='06:00',
            closing_time='21:00',
            is_active=True
        )
        self.client.force_login(self.admin)

    def test_facility_list_displays_management_controls(self):
        response = self.client.get(reverse('facility_list'))

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(
            response,
            'Reservation/admin/facilities/FacilityList.html'
        )
        self.assertContains(response, 'Facility Directory')
        self.assertContains(response, 'Add Facility')
        self.assertContains(response, self.facility.name)
        self.assertContains(response, self.facility.facility_code)
        self.assertContains(
            response,
            reverse('facility_update', args=[self.facility.id])
        )
        self.assertContains(
            response,
            reverse('facility_archive', args=[self.facility.id])
        )
        self.assertNotContains(response, 'Schedule a Closure')

    def test_facility_search_filters_the_directory(self):
        response = self.client.get(
            reverse('facility_list'),
            {'search': 'LIB-201'}
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, self.facility.name)
        self.assertNotContains(response, self.other_facility.name)
        self.assertContains(response, 'Results for')

    def test_archive_action_marks_facility_inactive_and_logs_it(self):
        response = self.client.post(
            reverse('facility_archive', args=[self.facility.id])
        )

        self.assertRedirects(response, reverse('facility_list'))
        self.facility.refresh_from_db()
        self.assertFalse(self.facility.is_active)
        self.assertTrue(
            AuditLog.objects.filter(
                actor=self.admin,
                action='FACILITY_ARCHIVED',
                reference=f'Facility #{self.facility.pk}'
            ).exists()
        )


class InvalidFilterHandlingTest(TestCase):

    def setUp(self):
        self.admin = User.objects.create_user(
            username='filteradmin',
            password='TestPassword123!',
            role='ADMIN'
        )
        self.basic_user = User.objects.create_user(
            username='filteruser',
            password='TestPassword123!',
            role='BASIC_USER'
        )
        self.category = FacilityCategory.objects.create(
            name='Filter Test Spaces',
            is_active=True
        )
        self.facility = Facility.objects.create(
            facility_code='FLT-101',
            name='Filter Test Hall',
            category=self.category,
            location='Main Campus',
            capacity=30,
            description='Facility used for filter validation tests.',
            opening_time='08:00',
            closing_time='18:00',
            is_active=True
        )
        self.reservation = Reservation.objects.create(
            user=self.basic_user,
            facility=self.facility,
            event_name='Filter Validation Event',
            purpose='Verify malformed filters are handled safely.',
            expected_attendees=15,
            start_datetime=timezone.now() + timedelta(days=3),
            end_datetime=timezone.now() + timedelta(days=3, hours=1),
            status='PENDING'
        )

    def test_reservation_queue_ignores_malformed_date_and_facility(self):
        self.client.force_login(self.admin)

        response = self.client.get(
            reverse('reservation_queue'),
            {
                'date': '2026-02-30',
                'facility': 'not-a-facility',
            }
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['date_filter'], '')
        self.assertEqual(response.context['facility_filter'], '')
        self.assertContains(response, self.reservation.event_name)

    def test_reports_ignore_malformed_date_range(self):
        self.client.force_login(self.admin)

        response = self.client.get(
            reverse('reports'),
            {
                'start_date': 'invalid-start',
                'end_date': '2026-13-40',
            }
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['start_date'], '')
        self.assertEqual(response.context['end_date'], '')
        self.assertEqual(response.context['total_reservations'], 1)

    def test_csv_export_ignores_malformed_date_range(self):
        self.client.force_login(self.admin)

        response = self.client.get(
            reverse('export_reservations_csv'),
            {
                'start_date': 'not-a-date',
                'end_date': '2026-02-30',
            }
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'text/csv')
        self.assertContains(response, self.reservation.event_name)

    def test_facility_browse_ignores_malformed_category(self):
        self.client.force_login(self.basic_user)

        for malformed_category in [
            'not-a-category',
            '-1',
            '999999999999999999999999999999',
        ]:
            with self.subTest(category=malformed_category):
                response = self.client.get(
                    reverse('browse_facilities'),
                    {'category': malformed_category}
                )

                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.context['category_filter'], '')
                self.assertContains(response, self.facility.name)

    def test_admin_calendar_ignores_invalid_facility_ids(self):
        self.client.force_login(self.admin)

        for invalid_facility in [
            'not-a-facility',
            '-1',
            '999999999999999999999999999999',
        ]:
            with self.subTest(facility=invalid_facility):
                response = self.client.get(
                    reverse('admin_calendar'),
                    {'facility': invalid_facility}
                )

                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.context['facility_filter'], '')


class ReservationDecisionReasonTest(TestCase):

    def setUp(self):
        self.admin = User.objects.create_user(
            username='decisionadmin',
            password='TestPassword123!',
            role='ADMIN'
        )
        self.requester = User.objects.create_user(
            username='decisionrequester',
            password='TestPassword123!',
            role='BASIC_USER'
        )
        self.category = FacilityCategory.objects.create(
            name='Decision Test Spaces',
            is_active=True
        )
        self.facility = Facility.objects.create(
            facility_code='DEC-101',
            name='Decision Test Hall',
            category=self.category,
            location='Main Campus',
            capacity=40,
            description='Facility used for decision reason tests.',
            opening_time='08:00',
            closing_time='18:00',
            is_active=True
        )
        reservation_start = (
            timezone.localtime(timezone.now())
            + timedelta(days=4)
        ).replace(
            hour=10,
            minute=0,
            second=0,
            microsecond=0
        )
        self.reservation = Reservation.objects.create(
            user=self.requester,
            facility=self.facility,
            event_name='Decision Reason Event',
            purpose='Verify approval decision metadata.',
            expected_attendees=20,
            start_datetime=reservation_start,
            end_datetime=reservation_start + timedelta(hours=1),
            status='PENDING'
        )
        self.client.force_login(self.admin)

    def test_approval_form_requires_reason(self):
        response = self.client.get(
            reverse(
                'reservation_detail_admin',
                args=[self.reservation.pk]
            )
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Approval Reason')
        self.assertContains(response, 'id="approval-reason"')
        self.assertContains(response, 'required')
        self.assertNotContains(response, 'Decision Note (optional)')

    def test_approval_without_reason_is_rejected(self):
        response = self.client.post(
            reverse(
                'reservation_approve',
                args=[self.reservation.pk]
            ),
            {'decision_reason': '   '},
            follow=True
        )

        self.reservation.refresh_from_db()
        self.assertEqual(self.reservation.status, 'PENDING')
        self.assertIsNone(self.reservation.decision_by)
        self.assertIsNone(self.reservation.decision_at)
        self.assertEqual(self.reservation.decision_reason, '')
        self.assertContains(
            response,
            'An approval reason is required.'
        )
        self.assertFalse(
            AuditLog.objects.filter(
                action='RESERVATION_APPROVED',
                reference=f'Reservation #{self.reservation.pk}'
            ).exists()
        )

    def test_approval_service_rejects_blank_reason(self):
        with self.assertRaisesMessage(
            ValidationError,
            'An approval reason is required.'
        ):
            approve_reservation(
                reservation_id=self.reservation.pk,
                admin_user=self.admin,
                reason=''
            )

        self.reservation.refresh_from_db()
        self.assertEqual(self.reservation.status, 'PENDING')

    def test_approval_records_actor_timestamp_and_reason(self):
        reason = 'Schedule and facility requirements are satisfied.'

        approve_reservation(
            reservation_id=self.reservation.pk,
            admin_user=self.admin,
            reason=reason
        )

        self.reservation.refresh_from_db()
        self.assertEqual(self.reservation.status, 'APPROVED')
        self.assertEqual(self.reservation.decision_by, self.admin)
        self.assertIsNotNone(self.reservation.decision_at)
        self.assertEqual(self.reservation.decision_reason, reason)

        audit = AuditLog.objects.get(
            action='RESERVATION_APPROVED',
            reference=f'Reservation #{self.reservation.pk}'
        )
        self.assertEqual(audit.actor, self.admin)
        self.assertIsNotNone(audit.timestamp)
        self.assertEqual(audit.description, reason)


class FacilityUtilizationCsvExportTest(TestCase):

    def setUp(self):
        self.admin = User.objects.create_user(
            username='reportadmin',
            password='TestPassword123!',
            role='ADMIN'
        )
        self.basic_user = User.objects.create_user(
            username='reportuser',
            password='TestPassword123!',
            role='BASIC_USER'
        )
        self.category = FacilityCategory.objects.create(
            name='Report Test Spaces',
            is_active=True
        )
        self.facility = Facility.objects.create(
            facility_code='RPT-101',
            name='Report Test Hall',
            category=self.category,
            location='Main Campus',
            capacity=60,
            description='Facility used for utilization report tests.',
            opening_time='08:00',
            closing_time='18:00',
            is_active=True
        )
        self.unused_facility = Facility.objects.create(
            facility_code='RPT-102',
            name='Unused Report Room',
            category=self.category,
            location='Main Campus',
            capacity=20,
            description='Facility with no usage in the selected range.',
            opening_time='08:00',
            closing_time='18:00',
            is_active=True
        )
        self.report_date = (
            timezone.localtime(timezone.now())
            - timedelta(days=3)
        ).date()
        completed_start = timezone.make_aware(
            timezone.datetime.combine(
                self.report_date,
                timezone.datetime.strptime('09:00', '%H:%M').time()
            )
        )
        approved_start = completed_start + timedelta(hours=3)

        Reservation.objects.create(
            user=self.basic_user,
            facility=self.facility,
            event_name='Completed Report Event',
            purpose='Counted as a completed event.',
            expected_attendees=30,
            start_datetime=completed_start,
            end_datetime=completed_start + timedelta(hours=2),
            status='COMPLETED'
        )
        Reservation.objects.create(
            user=self.basic_user,
            facility=self.facility,
            event_name='Approved Report Event',
            purpose='Counted in booked hours.',
            expected_attendees=20,
            start_datetime=approved_start,
            end_datetime=approved_start + timedelta(hours=1, minutes=30),
            status='APPROVED'
        )
        Reservation.objects.create(
            user=self.basic_user,
            facility=self.facility,
            event_name='Pending Report Event',
            purpose='Excluded from utilization.',
            expected_attendees=10,
            start_datetime=approved_start + timedelta(days=1),
            end_datetime=approved_start + timedelta(days=1, hours=1),
            status='PENDING'
        )

    def csv_rows(self, response):
        return list(
            csv.reader(
                StringIO(response.content.decode('utf-8'))
            )
        )

    def test_report_page_links_both_csv_exports(self):
        self.client.force_login(self.admin)

        response = self.client.get(reverse('reports'))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Reservations CSV')
        self.assertContains(response, 'Facility Usage CSV')
        self.assertContains(
            response,
            reverse('export_facility_usage_csv')
        )

    def test_facility_utilization_csv_matches_filtered_report(self):
        self.client.force_login(self.admin)
        report_date = self.report_date.isoformat()

        response = self.client.get(
            reverse('export_facility_usage_csv'),
            {
                'start_date': report_date,
                'end_date': report_date,
            }
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'text/csv')
        self.assertIn(
            'facility_utilization_report.csv',
            response['Content-Disposition']
        )
        self.assertEqual(
            self.csv_rows(response),
            [
                [
                    'Facility Code',
                    'Facility',
                    'Completed Events',
                    'Booked Hours',
                ],
                [
                    self.facility.facility_code,
                    self.facility.name,
                    '1',
                    '3.50',
                ],
                [
                    self.unused_facility.facility_code,
                    self.unused_facility.name,
                    '0',
                    '0.00',
                ],
            ]
        )

    def test_facility_utilization_csv_handles_invalid_dates(self):
        self.client.force_login(self.admin)

        response = self.client.get(
            reverse('export_facility_usage_csv'),
            {
                'start_date': 'invalid',
                'end_date': '2026-02-30',
            }
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(self.csv_rows(response)), 3)

    def test_basic_user_cannot_export_facility_utilization(self):
        self.client.force_login(self.basic_user)

        response = self.client.get(
            reverse('export_facility_usage_csv')
        )

        self.assertRedirects(response, reverse('user_dashboard'))


class ClosureCreationTest(TestCase):

    def setUp(self):
        self.admin = User.objects.create_user(
            username='closureadmin',
            password='TestPassword123!',
            role='ADMIN'
        )
        self.requester = User.objects.create_user(
            username='closurerequester',
            password='TestPassword123!',
            role='BASIC_USER',
            first_name='Casey',
            last_name='Reyes'
        )
        self.category = FacilityCategory.objects.create(
            name='Closure Test Spaces',
            is_active=True
        )
        self.facility = Facility.objects.create(
            facility_code='CLS-101',
            name='Closure Test Hall',
            category=self.category,
            location='Administration Building',
            capacity=80,
            description='Facility used for closure workflow tests.',
            opening_time='07:00',
            closing_time='20:00',
            is_active=True
        )

        future_day = (
            timezone.localtime(timezone.now())
            + timedelta(days=7)
        )
        self.reservation_start = future_day.replace(
            hour=10,
            minute=0,
            second=0,
            microsecond=0
        )
        self.reservation_end = self.reservation_start + timedelta(hours=2)
        self.reservation = Reservation.objects.create(
            user=self.requester,
            facility=self.facility,
            event_name='Approved Faculty Workshop',
            purpose='Faculty development workshop.',
            expected_attendees=35,
            start_datetime=self.reservation_start,
            end_datetime=self.reservation_end,
            status='APPROVED',
            decision_by=self.admin,
            decision_at=timezone.now(),
            decision_reason='Schedule approved.'
        )
        self.client.force_login(self.admin)

    @staticmethod
    def as_datetime_local(value):
        return timezone.localtime(value).strftime('%Y-%m-%dT%H:%M')

    def test_closure_form_displays_correct_content(self):
        response = self.client.get(reverse('closure_create'))

        self.assertEqual(response.status_code, 200)
        self.assertTemplateUsed(
            response,
            'Reservation/admin/closures/ClosureForm.html'
        )
        self.assertContains(response, 'Schedule a facility closure')
        self.assertContains(response, 'Closure starts')
        self.assertContains(response, 'Closure ends')
        self.assertContains(response, 'Reason for closure')
        self.assertContains(response, reverse('closure_list'))
        self.assertNotContains(response, 'Category Information')
        self.assertNotContains(response, 'Back to Categories')

    def test_conflicting_reservations_are_displayed_and_block_creation(self):
        response = self.client.post(
            reverse('closure_create'),
            {
                'facility': self.facility.id,
                'start_datetime': self.as_datetime_local(
                    self.reservation_start + timedelta(minutes=30)
                ),
                'end_datetime': self.as_datetime_local(
                    self.reservation_end + timedelta(minutes=30)
                ),
                'reason': 'Emergency electrical inspection.',
            }
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(ClosureBlock.objects.count(), 0)
        self.assertEqual(
            response.context['conflicting_reservations'].count(),
            1
        )
        self.assertContains(response, 'conflicting')
        self.assertContains(response, 'reservation')
        self.assertContains(response, self.reservation.event_name)
        self.assertContains(response, self.requester.get_full_name())
        self.assertContains(
            response,
            reverse(
                'reservation_detail_admin',
                args=[self.reservation.id]
            )
        )

    def test_non_conflicting_closure_is_created_and_logged(self):
        closure_start = self.reservation_end
        closure_end = closure_start + timedelta(hours=2)

        response = self.client.post(
            reverse('closure_create'),
            {
                'facility': self.facility.id,
                'start_datetime': self.as_datetime_local(closure_start),
                'end_datetime': self.as_datetime_local(closure_end),
                'reason': 'Scheduled equipment inspection.',
            }
        )

        self.assertRedirects(response, reverse('closure_list'))
        closure = ClosureBlock.objects.get()
        self.assertEqual(closure.created_by, self.admin)
        self.assertEqual(closure.facility, self.facility)
        self.assertTrue(closure.is_active)
        self.assertTrue(
            AuditLog.objects.filter(
                actor=self.admin,
                action='CLOSURE_CREATED',
                reference=f'Closure #{closure.pk}'
            ).exists()
        )

    def test_cancelled_conflict_allows_closure_creation(self):
        cancellation_response = self.client.post(
            reverse(
                'reservation_cancel_admin',
                args=[self.reservation.id]
            ),
            {
                'reason': 'Facility required for emergency maintenance.'
            }
        )

        self.assertRedirects(
            cancellation_response,
            reverse(
                'reservation_detail_admin',
                args=[self.reservation.id]
            )
        )

        response = self.client.post(
            reverse('closure_create'),
            {
                'facility': self.facility.id,
                'start_datetime': self.as_datetime_local(
                    self.reservation_start + timedelta(minutes=30)
                ),
                'end_datetime': self.as_datetime_local(
                    self.reservation_end + timedelta(minutes=30)
                ),
                'reason': 'Emergency electrical inspection.',
            }
        )

        self.assertRedirects(response, reverse('closure_list'))
        self.assertEqual(ClosureBlock.objects.count(), 1)


class ClosureArchiveValidationTest(TestCase):

    def setUp(self):
        self.admin = User.objects.create_user(
            username='closurearchiveadmin',
            password='TestPassword123!',
            role='ADMIN'
        )
        self.requester = User.objects.create_user(
            username='closurearchiverequester',
            password='TestPassword123!',
            role='BASIC_USER'
        )
        self.category = FacilityCategory.objects.create(
            name='Closure Archive Spaces',
            is_active=True
        )
        self.facility = Facility.objects.create(
            facility_code='ARC-101',
            name='Closure Archive Hall',
            category=self.category,
            location='Main Campus',
            capacity=60,
            opening_time='07:00',
            closing_time='20:00',
            is_active=True
        )
        self.future_start = timezone.now() + timedelta(days=7)
        self.future_end = self.future_start + timedelta(hours=2)
        self.client.force_login(self.admin)

    def create_closure(self, start_datetime=None, end_datetime=None):
        return ClosureBlock.objects.create(
            facility=self.facility,
            start_datetime=start_datetime or self.future_start,
            end_datetime=end_datetime or self.future_end,
            reason='Preventive maintenance.',
            created_by=self.admin
        )

    def test_unused_future_closure_is_archived_and_logged(self):
        closure = self.create_closure()

        response = self.client.post(
            reverse('closure_archive', args=[closure.pk])
        )

        self.assertRedirects(response, reverse('closure_list'))
        closure.refresh_from_db()
        self.assertFalse(closure.is_active)
        self.assertIsNotNone(closure.archived_at)
        self.assertTrue(
            AuditLog.objects.filter(
                actor=self.admin,
                action='CLOSURE_ARCHIVED',
                reference=f'Closure #{closure.pk}'
            ).exists()
        )

    def test_started_closure_cannot_be_archived(self):
        closure = self.create_closure(
            start_datetime=timezone.now() - timedelta(hours=1),
            end_datetime=timezone.now() + timedelta(hours=1)
        )

        with self.assertRaisesMessage(
            ValidationError,
            'This closure has already started.'
        ):
            archive_closure_block(closure.pk, self.admin)

        closure.refresh_from_db()
        self.assertTrue(closure.is_active)
        self.assertIsNone(closure.archived_at)
        self.assertFalse(
            AuditLog.objects.filter(
                action='CLOSURE_ARCHIVED',
                reference=f'Closure #{closure.pk}'
            ).exists()
        )

    def test_closure_used_by_reservation_cannot_be_archived(self):
        closure = self.create_closure()
        Reservation.objects.create(
            user=self.requester,
            facility=self.facility,
            event_name='Reservation during closure',
            purpose='Validate closure archive protection.',
            expected_attendees=20,
            start_datetime=self.future_start + timedelta(minutes=30),
            end_datetime=self.future_end - timedelta(minutes=30),
            status='PENDING'
        )

        response = self.client.post(
            reverse('closure_archive', args=[closure.pk]),
            follow=True
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(
            response,
            'A reservation overlaps this closure period.'
        )
        closure.refresh_from_db()
        self.assertTrue(closure.is_active)
        self.assertIsNone(closure.archived_at)
        self.assertFalse(
            AuditLog.objects.filter(
                action='CLOSURE_ARCHIVED',
                reference=f'Closure #{closure.pk}'
            ).exists()
        )

    def test_non_overlapping_reservation_does_not_block_archive(self):
        closure = self.create_closure()
        Reservation.objects.create(
            user=self.requester,
            facility=self.facility,
            event_name='Earlier reservation',
            purpose='Validate half-open overlap handling.',
            expected_attendees=20,
            start_datetime=self.future_start - timedelta(hours=2),
            end_datetime=self.future_start,
            status='CANCELLED'
        )

        archive_closure_block(closure.pk, self.admin)

        closure.refresh_from_db()
        self.assertFalse(closure.is_active)
        self.assertIsNotNone(closure.archived_at)


class AdminReservationCancellationTest(TestCase):

    def setUp(self):
        self.admin = User.objects.create_user(
            username='cancellationadmin',
            password='TestPassword123!',
            role='ADMIN'
        )
        self.requester = User.objects.create_user(
            username='cancellationrequester',
            password='TestPassword123!',
            role='BASIC_USER'
        )
        self.category = FacilityCategory.objects.create(
            name='Cancellation Test Spaces',
            is_active=True
        )
        self.facility = Facility.objects.create(
            facility_code='CAN-101',
            name='Cancellation Test Hall',
            category=self.category,
            location='Main Campus',
            capacity=50,
            description='Facility used for cancellation workflow tests.',
            opening_time='08:00',
            closing_time='18:00',
            is_active=True
        )
        self.approval_time = timezone.now()
        self.reservation = Reservation.objects.create(
            user=self.requester,
            facility=self.facility,
            event_name='Approved Campus Event',
            purpose='Cancellation workflow test.',
            expected_attendees=20,
            start_datetime=timezone.now() + timedelta(days=5),
            end_datetime=timezone.now() + timedelta(days=5, hours=2),
            status='APPROVED',
            decision_by=self.admin,
            decision_at=self.approval_time,
            decision_reason='Original approval note.'
        )
        self.url = reverse(
            'reservation_cancel_admin',
            args=[self.reservation.id]
        )

    def test_approved_reservation_displays_cancellation_form(self):
        self.client.force_login(self.admin)

        response = self.client.get(
            reverse(
                'reservation_detail_admin',
                args=[self.reservation.id]
            )
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Cancel Reservation')
        self.assertContains(response, self.url)
        self.assertContains(response, 'Cancellation Reason')
        self.assertContains(response, 'name="reason"')
        self.assertContains(response, 'required')

    def test_admin_can_cancel_approved_reservation_with_reason(self):
        self.client.force_login(self.admin)
        reason = 'The facility is needed for urgent repairs.'

        response = self.client.post(
            self.url,
            {'reason': reason}
        )

        self.assertRedirects(
            response,
            reverse(
                'reservation_detail_admin',
                args=[self.reservation.id]
            )
        )
        self.reservation.refresh_from_db()
        self.assertEqual(self.reservation.status, 'CANCELLED')
        self.assertEqual(self.reservation.decision_by, self.admin)
        self.assertEqual(
            self.reservation.decision_reason,
            'Original approval note.'
        )
        self.assertEqual(
            self.reservation.decision_at,
            self.approval_time
        )

        audit = AuditLog.objects.get(
            action='RESERVATION_CANCELLED',
            reference=f'Reservation #{self.reservation.pk}'
        )
        self.assertEqual(audit.actor, self.admin)
        self.assertEqual(audit.description, reason)
        self.assertIsNotNone(audit.timestamp)

    def test_cancellation_requires_reason(self):
        self.client.force_login(self.admin)

        response = self.client.post(
            self.url,
            {'reason': '   '},
            follow=True
        )

        self.reservation.refresh_from_db()
        self.assertEqual(self.reservation.status, 'APPROVED')
        self.assertContains(
            response,
            'A cancellation reason is required.'
        )
        self.assertFalse(
            AuditLog.objects.filter(
                action='RESERVATION_CANCELLED',
                reference=f'Reservation #{self.reservation.pk}'
            ).exists()
        )

    def test_admin_cannot_cancel_non_approved_reservation(self):
        self.client.force_login(self.admin)
        self.reservation.status = 'CHECKED_IN'
        self.reservation.save(update_fields=['status', 'updated_at'])

        response = self.client.post(
            self.url,
            {'reason': 'Attempted invalid transition.'},
            follow=True
        )

        self.reservation.refresh_from_db()
        self.assertEqual(self.reservation.status, 'CHECKED_IN')
        self.assertContains(
            response,
            'Only an approved reservation can be cancelled.'
        )
        self.assertFalse(
            AuditLog.objects.filter(
                action='RESERVATION_CANCELLED',
                reference=f'Reservation #{self.reservation.pk}'
            ).exists()
        )

    def test_basic_user_cannot_use_admin_cancellation(self):
        self.client.force_login(self.requester)

        response = self.client.post(
            self.url,
            {'reason': 'Unauthorized cancellation attempt.'}
        )

        self.assertRedirects(response, reverse('user_dashboard'))
        self.reservation.refresh_from_db()
        self.assertEqual(self.reservation.status, 'APPROVED')

    def test_get_request_does_not_cancel_reservation(self):
        self.client.force_login(self.admin)

        response = self.client.get(self.url)

        self.assertRedirects(
            response,
            reverse(
                'reservation_detail_admin',
                args=[self.reservation.id]
            )
        )
        self.reservation.refresh_from_db()
        self.assertEqual(self.reservation.status, 'APPROVED')


class CompetingApprovalTest(TestCase):

    def setUp(self):
        # ---------------------------------------------
        # BOOKING SETTINGS
        # ---------------------------------------------
        SystemSetting.objects.create(
            max_event_duration_hours=4,
            advance_booking_days=30
        )

        # ---------------------------------------------
        # ADMIN
        # ---------------------------------------------
        self.admin = User.objects.create_user(
            username='testadmin',
            password='TestPassword123!',
            role='ADMIN'
        )

        # ---------------------------------------------
        # BASIC USERS
        # ---------------------------------------------
        self.user_one = User.objects.create_user(
            username='basicuser1',
            password='TestPassword123!',
            role='BASIC_USER'
        )

        self.user_two = User.objects.create_user(
            username='basicuser2',
            password='TestPassword123!',
            role='BASIC_USER'
        )

        # ---------------------------------------------
        # FACILITY
        # ---------------------------------------------
        self.category = FacilityCategory.objects.create(
            name='Testing Category',
            is_active=True
        )

        self.facility = Facility.objects.create(
            facility_code='TEST001',
            name='Testing Facility',
            category=self.category,
            location='Testing Building',
            capacity=50,
            description='Facility used for reservation tests.',
            opening_time='08:00',
            closing_time='18:00',
            is_active=True
        )

        # ---------------------------------------------
        # FUTURE OVERLAPPING SCHEDULE
        # ---------------------------------------------
        future_date = (
            timezone.localtime(timezone.now())
            + timedelta(days=5)
        ).date()

        self.start_time = timezone.make_aware(
            timezone.datetime.combine(
                future_date,
                timezone.datetime.strptime(
                    '10:00',
                    '%H:%M'
                ).time()
            )
        )

        self.end_time = self.start_time + timedelta(
            hours=2
        )

        # ---------------------------------------------
        # TWO PENDING RESERVATIONS
        # SAME FACILITY + SAME TIME
        # ---------------------------------------------
        self.reservation_one = Reservation.objects.create(
            user=self.user_one,
            facility=self.facility,
            event_name='Test Event One',
            purpose='Competing approval test.',
            expected_attendees=20,
            start_datetime=self.start_time,
            end_datetime=self.end_time,
            status='PENDING'
        )

        self.reservation_two = Reservation.objects.create(
            user=self.user_two,
            facility=self.facility,
            event_name='Test Event Two',
            purpose='Competing approval test.',
            expected_attendees=20,
            start_datetime=self.start_time,
            end_datetime=self.end_time,
            status='PENDING'
        )

    def test_only_one_overlapping_reservation_can_be_approved(self):
        # ---------------------------------------------
        # APPROVE FIRST RESERVATION
        # ---------------------------------------------
        approve_reservation(
            reservation_id=self.reservation_one.id,
            admin_user=self.admin,
            reason='First reservation approved.'
        )

        self.reservation_one.refresh_from_db()

        self.assertEqual(
            self.reservation_one.status,
            'APPROVED'
        )

        # ---------------------------------------------
        # SECOND APPROVAL MUST FAIL
        # ---------------------------------------------
        with self.assertRaises(ValidationError):
            approve_reservation(
                reservation_id=self.reservation_two.id,
                admin_user=self.admin,
                reason='Attempting second approval.'
            )

        self.reservation_two.refresh_from_db()

        # ---------------------------------------------
        # SECOND RESERVATION MUST REMAIN PENDING
        # ---------------------------------------------
        self.assertEqual(
            self.reservation_two.status,
            'PENDING'
        )

        # ---------------------------------------------
        # EXACTLY ONE APPROVED RESERVATION
        # ---------------------------------------------
        approved_count = Reservation.objects.filter(
            facility=self.facility,
            status='APPROVED',
            start_datetime__lt=self.end_time,
            end_datetime__gt=self.start_time
        ).count()

        self.assertEqual(
            approved_count,
            1
        )


class ConcurrentApprovalTest(TransactionTestCase):

    def setUp(self):
        self.admin_one = User.objects.create_user(
            username='concurrencyadmin1',
            password='TestPassword123!',
            role='ADMIN'
        )
        self.admin_two = User.objects.create_user(
            username='concurrencyadmin2',
            password='TestPassword123!',
            role='ADMIN'
        )
        self.user_one = User.objects.create_user(
            username='concurrentuser1',
            password='TestPassword123!',
            role='BASIC_USER'
        )
        self.user_two = User.objects.create_user(
            username='concurrentuser2',
            password='TestPassword123!',
            role='BASIC_USER'
        )
        self.category = FacilityCategory.objects.create(
            name='Concurrent Booking Spaces',
            is_active=True
        )
        self.facility = Facility.objects.create(
            facility_code='CON-101',
            name='Concurrency Test Hall',
            category=self.category,
            location='Main Campus',
            capacity=40,
            description='Facility used for concurrent approval tests.',
            opening_time='08:00',
            closing_time='18:00',
            is_active=True
        )

        self.target_start = (
            timezone.localtime(timezone.now())
            + timedelta(days=5)
        ).replace(
            hour=10,
            minute=0,
            second=0,
            microsecond=0
        )
        self.target_end = self.target_start + timedelta(hours=2)

        self.reservation_one = Reservation.objects.create(
            user=self.user_one,
            facility=self.facility,
            event_name='Concurrent Event One',
            purpose='First simultaneous approval request.',
            expected_attendees=20,
            start_datetime=self.target_start,
            end_datetime=self.target_end,
            status='PENDING'
        )
        self.reservation_two = Reservation.objects.create(
            user=self.user_two,
            facility=self.facility,
            event_name='Concurrent Event Two',
            purpose='Second simultaneous approval request.',
            expected_attendees=20,
            start_datetime=self.target_start,
            end_datetime=self.target_end,
            status='PENDING'
        )
        self.start_barrier = Barrier(2)

    def approve_concurrently(self, approval_attempt):
        reservation_id, administrator_id = approval_attempt
        close_old_connections()

        try:
            administrator = User.objects.get(pk=administrator_id)
            self.start_barrier.wait()
            approve_reservation(
                reservation_id=reservation_id,
                admin_user=administrator,
                reason='Concurrent approval test.'
            )
            return 'approved', administrator_id

        except ValidationError:
            return 'conflict', administrator_id

        finally:
            close_old_connections()

    def test_simultaneous_approvals_allow_exactly_one_booking(self):
        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(
                executor.map(
                    self.approve_concurrently,
                    [
                        (
                            self.reservation_one.pk,
                            self.admin_one.pk,
                        ),
                        (
                            self.reservation_two.pk,
                            self.admin_two.pk,
                        ),
                    ]
                )
            )

        self.assertCountEqual(
            [outcome for outcome, _ in results],
            ['approved', 'conflict']
        )
        self.assertSetEqual(
            {administrator_id for _, administrator_id in results},
            {self.admin_one.pk, self.admin_two.pk}
        )

        approved_reservation = Reservation.objects.get(
            facility=self.facility,
            status='APPROVED'
        )
        self.assertIn(
            approved_reservation.decision_by_id,
            [self.admin_one.pk, self.admin_two.pk]
        )
        self.assertEqual(
            AuditLog.objects.filter(
                action='RESERVATION_APPROVED'
            ).count(),
            1
        )

    def reschedule_concurrently(self, reschedule_attempt):
        reservation_id, administrator_id = reschedule_attempt
        close_old_connections()

        try:
            administrator = User.objects.get(pk=administrator_id)
            self.start_barrier.wait()
            reschedule_reservation(
                reservation_id=reservation_id,
                admin_user=administrator,
                new_start_datetime=self.target_start,
                new_end_datetime=self.target_end,
                reason='Concurrent rescheduling test.'
            )
            return 'rescheduled', administrator_id

        except ValidationError:
            return 'conflict', administrator_id

        finally:
            close_old_connections()

    def test_simultaneous_reschedules_allow_exactly_one_booking(self):
        self.reservation_one.start_datetime = (
            self.target_start - timedelta(hours=2)
        )
        self.reservation_one.end_datetime = (
            self.target_start - timedelta(hours=1)
        )
        self.reservation_one.status = 'APPROVED'
        self.reservation_one.save(
            update_fields=[
                'start_datetime',
                'end_datetime',
                'status',
                'updated_at',
            ]
        )

        self.reservation_two.start_datetime = (
            self.target_end + timedelta(hours=1)
        )
        self.reservation_two.end_datetime = (
            self.target_end + timedelta(hours=2)
        )
        self.reservation_two.status = 'APPROVED'
        self.reservation_two.save(
            update_fields=[
                'start_datetime',
                'end_datetime',
                'status',
                'updated_at',
            ]
        )

        with ThreadPoolExecutor(max_workers=2) as executor:
            results = list(
                executor.map(
                    self.reschedule_concurrently,
                    [
                        (
                            self.reservation_one.pk,
                            self.admin_one.pk,
                        ),
                        (
                            self.reservation_two.pk,
                            self.admin_two.pk,
                        ),
                    ]
                )
            )

        self.assertCountEqual(
            [outcome for outcome, _ in results],
            ['rescheduled', 'conflict']
        )
        self.assertSetEqual(
            {administrator_id for _, administrator_id in results},
            {self.admin_one.pk, self.admin_two.pk}
        )
        self.assertEqual(
            Reservation.objects.filter(
                facility=self.facility,
                status='APPROVED',
                start_datetime=self.target_start,
                end_datetime=self.target_end
            ).count(),
            1
        )
