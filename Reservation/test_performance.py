"""Bounded admin lists and dashboard aggregation without changing report scope."""
from datetime import datetime, time, timedelta
from unittest.mock import patch
from urllib.parse import parse_qs

from django.contrib.messages.storage.fallback import FallbackStorage
from django.test import RequestFactory, TestCase
from django.urls import resolve, reverse
from django.utils import timezone

from .models import AuditLog, ClosureBlock, Facility, FacilityCategory, Reservation, User
from .views import admin_dashboard


class PerformanceTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.admin = User.objects.create_user(username='performance-admin', role='ADMIN')
        cls.user = User.objects.create_user(username='performance-user', role='BASIC_USER')
        category = FacilityCategory.objects.create(name='Performance rooms')
        cls.facility = Facility.objects.create(facility_code='PERF-1', name='Performance room',
            category=category, location='Campus', capacity=30,
            opening_time=time(8), closing_time=time(18))
        cls.start = timezone.make_aware(datetime(2026, 10, 20, 9))
        Reservation.objects.bulk_create([
            Reservation(user=cls.user, facility=cls.facility, event_name=f'Event {i}',
                purpose='Review', expected_attendees=3, start_datetime=cls.start,
                end_datetime=cls.start + timedelta(hours=1), status='COMPLETED')
            for i in range(31)
        ])
        ClosureBlock.objects.bulk_create([
            ClosureBlock(facility=cls.facility, created_by=cls.admin, reason=f'Closure {i}',
                start_datetime=cls.start, end_datetime=cls.start + timedelta(hours=1))
            for i in range(31)
        ])
        AuditLog.objects.bulk_create([
            AuditLog(actor=cls.admin, action='PERFORMANCE_REVIEW', description=f'Entry {i}')
            for i in range(31)
        ])
        User.objects.bulk_create([
            User(username=f'performance-person-{i}', role='BASIC_USER') for i in range(30)
        ])

    def setUp(self):
        self.client.force_login(self.admin)

    def test_admin_lists_are_bounded_and_stable_across_pages(self):
        for route, key in [('user_management', 'users'), ('closure_list', 'closures'),
                           ('reports', 'reservations'), ('audit_logs', 'logs')]:
            with self.subTest(route=route):
                first = self.client.get(reverse(route))
                second = self.client.get(reverse(route), {'page': 2})
                self.assertEqual(first.status_code, 200)
                self.assertEqual(len(first.context[key]), 25)
                self.assertEqual(len(second.context[key]), 6)
                first_ids = {row.pk for row in first.context[key]}
                second_ids = {row.pk for row in second.context[key]}
                self.assertFalse(first_ids & second_ids)
                self.assertEqual(len(first_ids | second_ids), 31)
                self.assertContains(first, 'Next page')
                self.assertContains(second, 'Previous page')

    def test_pagination_preserves_repeated_report_filters_and_complete_totals(self):
        params = {'facility': [str(self.facility.pk), '999999'],
                  'start_date': '2026-10-20', 'end_date': '2026-10-20', 'page': '2'}
        response = self.client.get(reverse('reports'), params)
        self.assertEqual(response.context['total_reservations'], 31)
        self.assertEqual(response.context['completed_reservations'], 31)
        self.assertEqual(response.context['total_booked_hours'], 31)
        query = parse_qs(response.context['directory_query'])
        self.assertEqual(query['facility'], params['facility'])
        self.assertEqual(query['start_date'], ['2026-10-20'])
        self.assertNotIn('page', query)
        # Export continues to include every matching reservation, independent of page.
        exported = self.client.get(reverse('export_reservations_csv'), params)
        self.assertEqual(len(exported.content.decode().splitlines()), 32)

    def test_search_remains_applied_on_later_pages(self):
        response = self.client.get(reverse('audit_logs'), {'search': 'PERFORMANCE_REVIEW', 'page': 2})
        self.assertEqual(len(response.context['logs']), 6)
        self.assertEqual(parse_qs(response.context['directory_query'])['search'], ['PERFORMANCE_REVIEW'])
        empty = self.client.get(reverse('audit_logs'), {'search': 'no-matching-log', 'page': 2})
        self.assertEqual(len(empty.context['logs']), 0)

    def test_invalid_and_out_of_range_pages_have_safe_fallbacks(self):
        for route in ['user_management', 'closure_list', 'reports', 'audit_logs']:
            for value, expected in [('invalid', 1), ('99999', 2)]:
                with self.subTest(route=route, value=value):
                    response = self.client.get(reverse(route), {'page': value})
                    self.assertEqual(response.status_code, 200)
                    self.assertEqual(response.context['page_obj'].number, expected)

    def test_dashboard_uses_five_view_queries_and_local_month_boundaries(self):
        now = timezone.make_aware(datetime(2026, 10, 25, 12))
        # UTC date is September 30; the chart must count this in local October.
        Reservation.objects.create(user=self.user, facility=self.facility,
            event_name='Local midnight', purpose='Review', expected_attendees=3,
            start_datetime=timezone.make_aware(datetime(2026, 10, 1, 0, 15)),
            end_datetime=timezone.make_aware(datetime(2026, 10, 1, 1, 15)), status='PENDING')
        request = RequestFactory().get(reverse('admin_dashboard'))
        request.user = self.admin
        request.session = {}
        request._messages = FallbackStorage(request)
        request.resolver_match = resolve(request.path)
        with patch('Reservation.views.timezone.now', return_value=now):
            with self.assertNumQueries(5):
                response = admin_dashboard(request)
            rendered = self.client.get(reverse('admin_dashboard'))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(rendered.context['monthly_labels'],
            ['May 2026', 'Jun 2026', 'Jul 2026', 'Aug 2026', 'Sep 2026', 'Oct 2026'])
        self.assertEqual(rendered.context['monthly_booking_data'], [0, 0, 0, 0, 0, 32])
        self.assertEqual(rendered.context['completed_events'], 31)
        # The authenticated request expires the October 1 pending fixture.
        self.assertEqual(rendered.context['pending_requests'], 0)
        self.assertEqual(Reservation.objects.get(event_name='Local midnight').status, 'CANCELLED')

    def test_pagination_does_not_bypass_admin_permissions(self):
        self.client.force_login(self.user)
        for route in ['user_management', 'closure_list', 'reports', 'audit_logs']:
            response = self.client.get(reverse(route), {'page': 2})
            self.assertRedirects(response, reverse('user_dashboard'), fetch_redirect_response=False)
