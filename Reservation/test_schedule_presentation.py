"""User schedule views distinguish confirmed bookings from request history."""
from datetime import time, timedelta
from unittest.mock import patch

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from .models import Facility, FacilityCategory, Reservation, User


class SchedulePresentationTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username='schedule-owner')
        cls.other = User.objects.create_user(username='schedule-other')
        category = FacilityCategory.objects.create(name='Schedule rooms')
        cls.facility = Facility.objects.create(facility_code='SCHEDULE-1', name='Study room',
            category=category, location='Campus', capacity=20, opening_time=time(8), closing_time=time(20))

    def setUp(self):
        self.client.force_login(self.user)
        self.now = timezone.now().replace(second=0, microsecond=0)

    def booking(self, name, start, end, status='APPROVED', user=None):
        # Bulk fixture insertion avoids unrelated notification side effects.
        return Reservation.objects.bulk_create([Reservation(user=user or self.user,
            facility=self.facility, event_name=name, purpose='Study', expected_attendees=5,
            start_datetime=self.now+timedelta(minutes=start),
            end_datetime=self.now+timedelta(minutes=end), status=status)])[0]

    def page(self, route, **params):
        with patch('Reservation.views.timezone.now', return_value=self.now):
            return self.client.get(reverse(route), params)

    def test_home_ongoing_confirmed_booking_takes_priority_over_future(self):
        ongoing = self.booking('Happening', -30, 30, 'CHECKED_IN')
        future = self.booking('Next confirmed', 60, 120)
        self.booking('Awaiting review', 5, 65, 'PENDING')
        response = self.page('user_dashboard')
        self.assertEqual(response.context['highlighted_reservation'], ongoing)
        self.assertTrue(response.context['has_ongoing_reservation'])
        self.assertEqual(response.context['upcoming_reservations'], [future])
        self.assertContains(response, 'Currently happening')
        self.assertNotContains(response, 'Awaiting review')

    def test_home_nearest_confirmed_and_stable_future_limit(self):
        bookings = [self.booking(f'Booking {i}', 60+i*30, 80+i*30) for i in range(7)]
        self.booking('Other person', 1, 10, user=self.other)
        self.booking('Pending first', 1, 10, 'PENDING')
        response = self.page('user_dashboard')
        self.assertEqual(response.context['highlighted_reservation'], bookings[0])
        self.assertEqual(response.context['upcoming_reservations'], bookings[:5])
        self.assertContains(response, 'Next on your schedule')
        self.assertFalse(response.context['has_ongoing_reservation'])

    def test_terminal_and_pending_records_never_appear_as_confirmed_home_bookings(self):
        for status in ('PENDING', 'REJECTED', 'CANCELLED', 'COMPLETED', 'NO_SHOW'):
            self.booking(f'Hidden {status}', 60, 120, status)
        self.booking('Already ended', -60, 0, 'CHECKED_IN')
        response = self.page('user_dashboard')
        self.assertIsNone(response.context['highlighted_reservation'])
        self.assertEqual(response.context['upcoming_reservations'], [])
        self.assertContains(response, 'No confirmed bookings ahead.')
        self.assertContains(response, 'Pending requests remain in My reservations')

    def test_upcoming_history_sorts_ongoing_first_then_nearest_future(self):
        far = self.booking('Tomorrow', 1440, 1500)
        near = self.booking('Later today', 60, 120, 'PENDING')
        ongoing = self.booking('In progress', -30, 30, 'CHECKED_IN')
        tied = self.booking('Same time', 60, 120)
        for status in ('REJECTED', 'CANCELLED', 'COMPLETED', 'NO_SHOW'):
            self.booking(f'Excluded {status}', 10, 20, status)
        self.booking('Private', -10, 20, user=self.other)
        response = self.page('my_reservations', period='upcoming')
        self.assertEqual(list(response.context['reservations']), [ongoing, near, tied, far])
        pending = self.page('my_reservations', period='upcoming', status='PENDING')
        self.assertEqual(list(pending.context['reservations']), [near])

    def test_past_includes_exact_end_boundary_and_orders_newest_first(self):
        older = self.booking('Older', -1440, -1380, 'COMPLETED')
        ended = self.booking('Just ended', -60, 0)
        upcoming = self.page('my_reservations', period='upcoming')
        self.assertEqual(list(upcoming.context['reservations']), [])
        past = self.page('my_reservations', period='past')
        self.assertEqual(list(past.context['reservations']), [ended, older])

    def test_future_check_in_is_confirmed_and_start_boundary_is_ongoing(self):
        starting = self.booking('Starting now', 0, 60)
        checked_in = self.booking('Early check in', 15, 75, 'CHECKED_IN')
        response = self.page('user_dashboard')
        self.assertEqual(response.context['highlighted_reservation'], starting)
        self.assertEqual(response.context['upcoming_reservations'], [checked_in])

    def test_pending_home_count_excludes_expired_requests_and_other_people(self):
        self.booking('Future pending', 60, 120, 'PENDING')
        expired = self.booking('Past pending', -120, -60, 'PENDING')
        self.booking('Approved', 90, 150)
        self.booking('Private pending', 60, 120, 'PENDING', user=self.other)
        response = self.page('user_dashboard')
        self.assertEqual(response.context['pending_request_count'], 1)
        self.assertContains(response, 'Awaiting approval · 1')
        expired.refresh_from_db()
        self.assertEqual(expired.status, 'CANCELLED')
        self.assertContains(response, '?status=PENDING&amp;period=all')
        filtered = self.page('my_reservations', status='PENDING', period='all')
        self.assertEqual(filtered.context['page_obj'].paginator.count, 1)

    def test_zero_pending_hides_home_shortcut(self):
        response = self.page('user_dashboard')
        self.assertEqual(response.context['pending_request_count'], 0)
        self.assertNotContains(response, 'Awaiting approval ·')

    def test_passed_start_requests_are_cancelled_and_removed_from_upcoming(self):
        before = self.booking('Waiting now', -30, 30, 'PENDING')
        boundary = self.booking('Starting pending', 0, 60, 'PENDING')
        self.booking('Future pending', 60, 120, 'PENDING')
        self.booking('Ongoing approved', -30, 30)
        self.booking('Ended pending', -120, -60, 'PENDING')
        response = self.page('my_reservations', period='upcoming')
        self.assertNotContains(response, 'Start time passed · Still pending')
        self.assertNotIn(before, list(response.context['reservations']))
        self.assertNotIn(boundary, list(response.context['reservations']))
        history = self.page('my_reservations', period='all')
        self.assertContains(history, 'Not approved before start', count=3)
        for booking in (before, boundary):
            booking.refresh_from_db()
            self.assertEqual(booking.status, 'CANCELLED')
        with patch('Reservation.views.timezone.now', return_value=self.now):
            detail = self.client.get(reverse('reservation_detail_user', args=[before.pk]))
        self.assertContains(detail, 'Automatically cancelled because')
        self.assertContains(detail, 'Submit a new request')
        self.assertNotContains(detail, reverse('reservation_cancel_user', args=[before.pk]))

    def test_future_pending_still_offers_cancel_without_passed_start_warning(self):
        booking = self.booking('Future request', 60, 120, 'PENDING')
        with patch('Reservation.views.timezone.now', return_value=self.now):
            detail = self.client.get(reverse('reservation_detail_user', args=[booking.pk]))
        self.assertContains(detail, reverse('reservation_cancel_user', args=[booking.pk]))
        self.assertNotContains(detail, 'Start time passed · Still pending')
