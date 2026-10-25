"""Presentation routing must retain server validation, permissions and messages."""
from datetime import datetime, time, timedelta
from urllib.parse import parse_qs, urlsplit

from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from .models import Amenity, Facility, FacilityCategory, Reservation, User


class WorkspaceEditorTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.admin = User.objects.create_user(username='editor-admin', role='ADMIN')
        cls.user = User.objects.create_user(username='editor-user', role='BASIC_USER')
        cls.category = FacilityCategory.objects.create(name='Editor rooms')
        cls.amenity = Amenity.objects.create(name='Editor projector')
        cls.facility = Facility.objects.create(
            facility_code='EDITOR-1', name='Editor room', category=cls.category,
            location='Main', capacity=30, opening_time=time(8), closing_time=time(20),
        )
        cls.start = timezone.make_aware(datetime.combine(
            timezone.localdate() + timedelta(days=3), time(9),
        ))
        cls.reservation = Reservation.objects.create(
            user=cls.user, facility=cls.facility, event_name='Editor event',
            purpose='Testing', expected_attendees=10, status='APPROVED',
            start_datetime=cls.start, end_datetime=cls.start + timedelta(hours=1),
        )

    def test_direct_admin_links_open_their_workspace_and_editor(self):
        self.client.force_login(self.admin)
        routes = [
            ('category_create', (), 'category_list', ()),
            ('category_update', (self.category.pk,), 'category_list', ()),
            ('amenity_create', (), 'amenity_list', ()),
            ('amenity_update', (self.amenity.pk,), 'amenity_list', ()),
            ('facility_create', (), 'facility_list', ()),
            ('facility_update', (self.facility.pk,), 'facility_list', ()),
            ('closure_create', (), 'closure_list', ()),
            ('system_settings', (), 'admin_dashboard', ()),
            ('reservation_reschedule', (self.reservation.pk,), 'reservation_detail_admin', (self.reservation.pk,)),
        ]
        for editor, args, home, home_args in routes:
            with self.subTest(editor=editor):
                endpoint = reverse(editor, args=args)
                response = self.client.get(endpoint)
                self.assertEqual(response.status_code, 302)
                target = urlsplit(response.url)
                self.assertEqual(target.path, reverse(home, args=home_args))
                self.assertEqual(parse_qs(target.query)['editor'], [endpoint])
                modal = self.client.get(endpoint, HTTP_X_SPASYO_EDITOR='1')
                self.assertEqual(modal.status_code, 200)
                self.assertIn('form', modal.context)

    def test_direct_user_links_preserve_preselected_facility(self):
        self.client.force_login(self.user)
        endpoint = reverse('reservation_create') + f'?facility={self.facility.pk}'
        response = self.client.get(endpoint)
        target = urlsplit(response.url)
        self.assertEqual(target.path, reverse('browse_facilities'))
        self.assertEqual(parse_qs(target.query)['editor'], [endpoint])
        modal = self.client.get(endpoint, HTTP_X_SPASYO_EDITOR='1')
        self.assertEqual(str(modal.context['form']['facility'].value()), str(self.facility.pk))
        profile = self.client.get(reverse('user_profile'))
        self.assertEqual(urlsplit(profile.url).path, reverse('user_dashboard'))

    def test_success_receipt_does_not_consume_flash_or_repeat_save(self):
        self.client.force_login(self.admin)
        response = self.client.post(
            reverse('category_create'), {'name': 'Saved editor category', 'is_active': 'on'},
            HTTP_X_SPASYO_EDITOR='1',
        )
        self.assertEqual(response.json(), {'saved': True, 'redirect_url': reverse('category_list')})
        self.assertEqual(FacilityCategory.objects.filter(name='Saved editor category').count(), 1)
        workspace = self.client.get(response.json()['redirect_url'])
        self.assertContains(workspace, 'created successfully')
        self.assertContains(workspace, 'Saved editor category')

    def test_invalid_admin_save_returns_bound_html_not_a_success_receipt(self):
        self.client.force_login(self.admin)
        response = self.client.post(reverse('category_create'), {'name': ''}, HTTP_X_SPASYO_EDITOR='1')
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response['Content-Type'].startswith('text/html'))
        self.assertFormError(response.context['form'], 'name', 'This field is required.')

    def test_reservation_duration_error_preserves_values_without_creating_booking(self):
        self.client.force_login(self.user)
        response = self.client.post(reverse('reservation_create'), {
            'facility': self.facility.pk, 'event_name': 'Five hour request', 'purpose': 'Testing errors',
            'expected_attendees': 12,
            'start_datetime': self.start.strftime('%Y-%m-%dT%H:%M'),
            'end_datetime': (self.start + timedelta(hours=5)).strftime('%Y-%m-%dT%H:%M'),
        }, HTTP_X_SPASYO_EDITOR='1')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'maximum event duration is 4 hours')
        self.assertEqual(response.context['form']['event_name'].value(), 'Five hour request')
        self.assertFalse(Reservation.objects.filter(event_name='Five hour request').exists())

    def test_successful_reservation_returns_detail_destination(self):
        self.client.force_login(self.user)
        start = self.start + timedelta(days=1)
        response = self.client.post(reverse('reservation_create'), {
            'facility': self.facility.pk, 'event_name': 'Valid editor request', 'purpose': 'Testing save',
            'expected_attendees': 12, 'start_datetime': start.strftime('%Y-%m-%dT%H:%M'),
            'end_datetime': (start + timedelta(hours=1)).strftime('%Y-%m-%dT%H:%M'),
        }, HTTP_X_SPASYO_EDITOR='1')
        saved = Reservation.objects.get(event_name='Valid editor request')
        self.assertEqual(response.json(), {'saved': True, 'redirect_url': reverse('reservation_detail_user', args=[saved.pk])})

    def test_editor_header_does_not_bypass_role_checks_or_authentication(self):
        response = self.client.get(reverse('category_create'), HTTP_X_SPASYO_EDITOR='1')
        self.assertRedirects(response, reverse('login'))
        self.client.force_login(self.user)
        response = self.client.post(reverse('category_create'), {'name': 'Unauthorized'}, HTTP_X_SPASYO_EDITOR='1')
        self.assertRedirects(response, reverse('user_dashboard'))
        self.assertFalse(FacilityCategory.objects.filter(name='Unauthorized').exists())

    def test_editor_post_still_requires_csrf(self):
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.admin)
        response = client.post(reverse('category_create'), {'name': 'Missing CSRF'}, HTTP_X_SPASYO_EDITOR='1')
        self.assertEqual(response.status_code, 403)
        self.assertFalse(FacilityCategory.objects.filter(name='Missing CSRF').exists())

    def test_closure_conflict_response_includes_details_outside_form(self):
        self.client.force_login(self.admin)
        response = self.client.post(reverse('closure_create'), {
            'facility': self.facility.pk, 'reason': 'Conflicting maintenance',
            'start_datetime': self.start.strftime('%Y-%m-%dT%H:%M'),
            'end_datetime': (self.start + timedelta(hours=1)).strftime('%Y-%m-%dT%H:%M'),
        }, HTTP_X_SPASYO_EDITOR='1')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'data-editor-content')
        self.assertContains(response, 'Editor event')
        self.assertTrue(response.context['form'].non_field_errors())


    def test_booking_policy_is_visible_inside_the_editor_form(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse('reservation_create'), HTTP_X_SPASYO_EDITOR='1')
        self.assertContains(response, '<p class="booking-policy" id="booking-policy">')
        self.assertContains(response, 'All times are Philippine local time (UTC+8).')
        self.assertContains(response, 'Requests require approval. Pending requests do not reserve a slot.')
        self.assertContains(response, 'aria-describedby="booking-policy"')
