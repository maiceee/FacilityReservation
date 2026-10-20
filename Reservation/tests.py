from datetime import timedelta

from django.conf import settings
from django.core.exceptions import ValidationError
from django.test import SimpleTestCase, TestCase
from django.utils import timezone

from .models import (
    User,
    FacilityCategory,
    Facility,
    Reservation,
    SystemSetting,
)
from .services import approve_reservation


class DjangoConfigurationTest(SimpleTestCase):

    def test_project_uses_manila_timezone(self):
        self.assertEqual(settings.TIME_ZONE, 'Asia/Manila')
        self.assertTrue(settings.USE_TZ)
        self.assertEqual(
            timezone.get_default_timezone_name(),
            'Asia/Manila'
        )


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
