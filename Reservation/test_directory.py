from datetime import time, timedelta
from unittest.mock import patch

from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from .models import Amenity, AuditLog, Facility, FacilityCategory, Reservation, User


class DirectoryWorkflowTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.admin = User.objects.create_user(username='directory-admin', role='ADMIN')
        cls.user = User.objects.create_user(username='directory-user')
        cls.category = FacilityCategory.objects.create(name='Rooms')
        cls.facility = Facility.objects.create(name='Room A', facility_code='A', category=cls.category,
            location='Main', capacity=30, opening_time=time(8), closing_time=time(20))
        cls.other = Facility.objects.create(name='Room B', facility_code='B', category=cls.category,
            location='Main', capacity=30, opening_time=time(8), closing_time=time(20))
        cls.amenities = [Amenity.objects.create(name=f'Amenity {i:02}') for i in range(31)]
        cls.inactive = Amenity.objects.create(name='Inactive projector', is_active=False)
        for facility in [cls.facility, cls.other]:
            Reservation.objects.create(user=cls.user, facility=facility, event_name=facility.name,
                purpose='Test', expected_attendees=10, status='COMPLETED',
                start_datetime=timezone.now(), end_datetime=timezone.now() + timedelta(hours=2))

    def setUp(self):
        self.client.force_login(self.admin)

    def post(self, selected, operation='deactivate', kind='amenity', **extra):
        return self.client.post(reverse('directory_bulk', args=[kind]),
            {'selected': selected, 'operation': operation, **extra})

    def test_directory_status_search_and_real_pagination(self):
        response = self.client.get(reverse('amenity_list'))
        self.assertEqual(len(response.context['amenities']), 25)
        self.assertEqual(response.context['page_obj'].paginator.count, 31)
        response = self.client.get(reverse('amenity_list'), {'state': 'inactive', 'search': 'projector'})
        self.assertEqual(list(response.context['amenities']), [self.inactive])
        response = self.client.get(reverse('amenity_list'), {'state': 'all', 'page': 2})
        self.assertEqual(len(response.context['amenities']), 7)
        self.assertContains(response, 'state=all')

    def test_bulk_changes_selected_only_and_audits_each(self):
        ids = [f'{a.pk}:1' for a in self.amenities[:2]]
        response = self.post(ids, state='all', search='Amenity', page='2')
        self.assertEqual(response.status_code, 302)
        self.assertIn('state=all', response.url)
        self.assertIn('page=2', response.url)
        self.assertEqual(Amenity.objects.filter(is_active=False).count(), 3)
        self.assertEqual(AuditLog.objects.filter(action='AMENITY_ARCHIVED').count(), 2)
        self.assertTrue(Amenity.objects.get(pk=self.amenities[2].pk).is_active)

    def test_activation_and_already_matching_skip(self):
        self.post([f'{self.inactive.pk}:0', f'{self.amenities[0].pk}:1'], operation='activate')
        self.inactive.refresh_from_db()
        self.assertTrue(self.inactive.is_active)
        self.assertEqual(AuditLog.objects.filter(action='AMENITY_REACTIVATED').count(), 1)

    def test_invalid_missing_duplicate_and_oversized_selection_are_atomic(self):
        for selection in [[], ['bad'], ['999999999:1', f'{self.amenities[0].pk}:1'],
                          [f'{self.amenities[0].pk}:1'] * 2, [f'{a.pk}:1' for a in self.amenities[:26]]]:
            self.post(selection)
        self.post([f'{self.amenities[0].pk}:1'], operation='delete')
        self.assertEqual(Amenity.objects.filter(is_active=True).count(), 31)
        self.assertEqual(AuditLog.objects.count(), 0)

    def test_stale_status_rejects_whole_batch(self):
        self.post([f'{self.inactive.pk}:1', f'{self.amenities[0].pk}:1'])
        self.assertTrue(Amenity.objects.get(pk=self.amenities[0].pk).is_active)
        self.assertEqual(AuditLog.objects.count(), 0)

    def test_facility_reactivation_requires_active_category(self):
        self.category.is_active = False
        self.category.save()
        self.facility.is_active = False
        self.facility.save()
        self.post([f'{self.facility.pk}:0'], 'activate', 'facility')
        self.facility.refresh_from_db()
        self.assertFalse(self.facility.is_active)

    def test_bulk_requires_admin_post_and_csrf(self):
        url = reverse('directory_bulk', args=['amenity'])
        self.assertEqual(self.client.get(url).status_code, 405)
        csrf_client = Client(enforce_csrf_checks=True)
        csrf_client.force_login(self.admin)
        self.assertEqual(csrf_client.post(url, {'selected': [f'{self.amenities[0].pk}:1'], 'operation': 'deactivate'}).status_code, 403)
        self.client.force_login(self.user)
        self.post([f'{self.amenities[0].pk}:1'])
        self.assertTrue(Amenity.objects.get(pk=self.amenities[0].pk).is_active)

    def test_audit_failure_rolls_back_record_updates(self):
        with patch('Reservation.directory.create_audit_log', side_effect=RuntimeError('test failure')):
            with self.assertRaises(RuntimeError):
                self.post([f'{self.amenities[0].pk}:1'])
        self.assertTrue(Amenity.objects.get(pk=self.amenities[0].pk).is_active)

    def test_report_selection_matches_both_exports(self):
        params = {'facility': [self.facility.pk]}
        response = self.client.get(reverse('reports'), params)
        self.assertEqual(response.context['total_reservations'], 1)
        self.assertEqual(len(response.context['facility_usage_rows']), 1)
        self.assertEqual(response.context['total_booked_hours'], 2)
        for route in ['export_reservations_csv', 'export_facility_usage_csv']:
            result = self.client.get(reverse(route), params).content.decode()
            self.assertIn('Room A', result)
            self.assertNotIn('Room B', result)
        response = self.client.get(reverse('reports'), {'facility': [self.facility.pk, self.other.pk]})
        self.assertEqual(response.context['total_reservations'], 2)
        response = self.client.get(reverse('reports'), {'facility': ['invalid']})
        self.assertEqual(response.context['total_reservations'], 0)
        self.assertEqual(len(response.context['facility_usage_rows']), 0)
