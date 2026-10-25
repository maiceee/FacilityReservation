"""Booking shortcuts stay editable; history filters remain scoped to the actor."""
from datetime import datetime, time, timedelta
from urllib.parse import parse_qs, urlsplit
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from unittest.mock import patch
from .models import Facility, FacilityCategory, Reservation, User


class BookingShortcutTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username='shortcut-user', role='BASIC_USER')
        cls.other = User.objects.create_user(username='shortcut-other', role='BASIC_USER')
        cls.category = FacilityCategory.objects.create(name='Study spaces')
        cls.facility = Facility.objects.create(facility_code='SHORT-1', name='Study Hall',
            category=cls.category, location='Main campus', capacity=30,
            opening_time=time(8), closing_time=time(18))
        cls.start = timezone.make_aware(datetime.combine(timezone.localdate()+timedelta(days=3), time(9)))
        cls.approved = Reservation.objects.create(user=cls.other, facility=cls.facility,
            event_name='Private other booking', purpose='Study', expected_attendees=5,
            start_datetime=cls.start, end_datetime=cls.start+timedelta(hours=1), status='APPROVED')

    def setUp(self):
        self.client.force_login(self.user)

    def editor(self, params=None):
        return self.client.get(reverse('reservation_create'), params or {}, HTTP_X_SPASYO_EDITOR='1')

    def test_slot_links_prefill_editable_local_times_without_creating_a_booking(self):
        response = self.client.get(reverse('facility_detail_user', args=[self.facility.pk]))
        count = Reservation.objects.count()
        links = [slot['booking_url'] for slot in response.context['available_slots'] if slot.get('booking_url')]
        self.assertTrue(links)
        for url in links:
            params = {key: value[0] for key, value in parse_qs(urlsplit(url).query).items()}
            start = datetime.strptime(params['start_datetime'], '%Y-%m-%dT%H:%M')
            end = datetime.strptime(params['end_datetime'], '%Y-%m-%dT%H:%M')
            self.assertGreater(end, start)
            self.assertLessEqual(end-start, timedelta(hours=1))
        form = self.editor(params).context['form']
        self.assertFalse(form.is_bound)
        self.assertEqual(str(form.initial['facility']), str(self.facility.pk))
        self.assertEqual(form.initial['start_datetime'], start)
        self.assertEqual(form.initial['end_datetime'], end)
        self.assertFalse(form.fields['start_datetime'].disabled)
        self.assertEqual(Reservation.objects.count(), count)

    def test_direct_slot_link_keeps_the_schedule_through_workspace_redirect(self):
        params = {'facility':self.facility.pk, 'start_datetime':'2026-12-01T09:00', 'end_datetime':'2026-12-01T10:00'}
        response = self.client.get(reverse('reservation_create'), params)
        self.assertEqual(response.status_code, 302)
        editor_url = parse_qs(urlsplit(response.url).query)['editor'][0]
        self.assertEqual(parse_qs(urlsplit(editor_url).query)['start_datetime'], ['2026-12-01T09:00'])

    def test_current_day_shortcut_allows_ten_minutes_to_complete_form(self):
        now = timezone.make_aware(datetime.combine(timezone.localdate(), time(12, 47, 20)))
        with patch('Reservation.views.timezone.now', return_value=now):
            response = self.client.get(reverse('facility_detail_user', args=[self.facility.pk]))
        today = [slot for slot in response.context['available_slots'] if slot['date'] == now.date() and slot.get('booking_url')]
        self.assertTrue(today)
        for slot in today:
            self.assertGreaterEqual(slot['booking_start'], now + timedelta(minutes=10))
            self.assertLess(slot['booking_start'], slot['end_datetime'])

    def test_shortcut_omitted_when_lead_time_reaches_closing(self):
        now = timezone.make_aware(datetime.combine(timezone.localdate(), time(17, 55)))
        with patch('Reservation.views.timezone.now', return_value=now):
            response = self.client.get(reverse('facility_detail_user', args=[self.facility.pk]))
        today = [slot for slot in response.context['available_slots'] if slot['date'] == now.date()]
        self.assertTrue(today)
        self.assertFalse(any(slot.get('booking_url') for slot in today))

    def test_past_start_is_attached_to_the_field_and_keeps_entered_data(self):
        count = Reservation.objects.count()
        response = self.client.post(reverse('reservation_create'), self.payload(timezone.now()-timedelta(minutes=1)), HTTP_X_SPASYO_EDITOR='1')
        form = response.context['form']
        self.assertIn('start_datetime', form.errors)
        self.assertIn('Choose a future start time', str(form.errors['start_datetime']))
        self.assertEqual(form['event_name'].value(), 'New study session')
        self.assertEqual(Reservation.objects.count(), count)

    def test_malformed_or_incomplete_prefill_is_ignored(self):
        for params in [{'start_datetime':'bad','end_datetime':'bad'},
                       {'start_datetime':'2026-12-01T09:00'},
                       {'start_datetime':'2026-12-01T10:00','end_datetime':'2026-12-01T09:00'}]:
            with self.subTest(params=params):
                form = self.editor(params).context['form']
                self.assertNotIn('start_datetime', form.initial)
                self.assertNotIn('end_datetime', form.initial)
                self.assertFalse(form.is_bound)

    def payload(self, start):
        return {'facility':self.facility.pk, 'event_name':'New study session', 'purpose':'Group study',
                'expected_attendees':5, 'start_datetime':start.strftime('%Y-%m-%dT%H:%M'),
                'end_datetime':(start+timedelta(hours=1)).strftime('%Y-%m-%dT%H:%M')}

    def test_stale_slot_is_rejected_by_existing_conflict_validation(self):
        count = Reservation.objects.count()
        response = self.client.post(reverse('reservation_create'), self.payload(self.start), HTTP_X_SPASYO_EDITOR='1')
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context['form'].errors)
        self.assertEqual(Reservation.objects.count(), count)

    def test_edited_post_values_override_prefill_and_save_as_pending(self):
        endpoint = reverse('reservation_create')+'?start_datetime=bad&end_datetime=bad'
        changed = self.start+timedelta(hours=2)
        response = self.client.post(endpoint, self.payload(changed), HTTP_X_SPASYO_EDITOR='1')
        self.assertTrue(response.json()['saved'])
        saved = Reservation.objects.get(user=self.user)
        self.assertEqual(saved.start_datetime, changed)
        self.assertEqual(saved.status, 'PENDING')

    def create_history(self, count=1, **kwargs):
        defaults = dict(user=self.user, facility=self.facility, event_name='Study session', purpose='Study',
            expected_attendees=5, start_datetime=self.start, end_datetime=self.start+timedelta(hours=1), status='PENDING')
        defaults.update(kwargs)
        return Reservation.objects.bulk_create([Reservation(**defaults) for _ in range(count)])

    def test_history_filters_combine_without_exposing_another_users_records(self):
        own = self.create_history()[0]
        self.create_history(event_name='Other activity', status='REJECTED')
        response = self.client.get(reverse('my_reservations'), {'search':'Study Hall','status':'PENDING','period':'upcoming'})
        self.assertEqual(list(response.context['reservations']), [own])
        self.assertNotContains(response, 'Private other booking')
        self.assertContains(response, 'value="PENDING" selected')
        response = self.client.get(reverse('my_reservations'), {'search':'Private other booking'})
        self.assertContains(response, 'No matching reservations')

    def test_history_period_and_invalid_filters(self):
        past = self.create_history(start_datetime=self.start-timedelta(days=10), end_datetime=self.start-timedelta(days=10)+timedelta(hours=1))[0]
        future = self.create_history()[0]
        response = self.client.get(reverse('my_reservations'), {'period':'past'})
        self.assertEqual(list(response.context['reservations']), [past])
        response = self.client.get(reverse('my_reservations'), {'period':'invalid','status':'invalid'})
        self.assertEqual(response.context['period_filter'], 'all')
        self.assertEqual(response.context['status_filter'], '')
        self.assertEqual(set(response.context['reservations']), {past,future})

    def test_history_pagination_preserves_filters_and_is_stable_for_tied_dates(self):
        records = self.create_history(count=28)
        response = self.client.get(reverse('my_reservations'), {'search':'Study','status':'PENDING','page':'2'})
        self.assertEqual(response.context['page_obj'].number, 2)
        self.assertEqual(len(response.context['reservations']), 3)
        self.assertEqual(response.context['page_obj'].paginator.count, 28)
        self.assertEqual([item.pk for item in response.context['reservations']], [item.pk for item in records[:3]][::-1])
        self.assertContains(response, 'search=Study&amp;status=PENDING&amp;period=all&amp;page=1')
        for page in ['bad','-1','999']:
            self.assertEqual(self.client.get(reverse('my_reservations'), {'page':page}).status_code, 200)

    def test_empty_history_has_first_booking_guidance(self):
        response = self.client.get(reverse('my_reservations'))
        self.assertContains(response, 'No reservations yet')
        self.assertNotContains(response, 'Filter your reservations')
