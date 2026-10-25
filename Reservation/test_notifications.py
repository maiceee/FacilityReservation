import json
from datetime import time, timedelta

from django.db import transaction
from django.test import Client, TestCase
from django.urls import reverse
from django.utils import timezone

from .models import Facility, FacilityCategory, Notification, Reservation, User


class NotificationTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username='inbox-user')
        cls.other = User.objects.create_user(username='inbox-other')
        cls.admin = User.objects.create_user(username='inbox-admin', role='ADMIN')
        cls.disabled = User.objects.create_user(username='inbox-disabled', role='ADMIN', is_active=False)
        cls.category = FacilityCategory.objects.create(name='Inbox rooms')
        cls.facility = Facility.objects.create(facility_code='INBOX-1', name='Meeting room',
            category=cls.category, location='Campus', capacity=20,
            opening_time=time(8), closing_time=time(18))

    def create_booking(self):
        start = timezone.now() + timedelta(days=1)
        return Reservation.objects.create(user=self.user, facility=self.facility,
            event_name='<script>Study session</script>', purpose='Study', expected_attendees=5,
            start_datetime=start, end_datetime=start + timedelta(hours=1))

    def login_as(self, user=None):
        self.client.force_login(user or self.user)

    def read(self, data):
        return self.client.post(reverse('notification_read'), json.dumps(data), content_type='application/json')

    def test_creation_targets_owner_and_active_administrators_only(self):
        booking = self.create_booking()
        self.assertSetEqual(set(Notification.objects.values_list('recipient_id', flat=True)),
                            {self.user.pk, self.admin.pk})
        self.assertEqual(Notification.objects.filter(reservation=booking).count(), 2)

    def test_status_and_schedule_changes_notify_both_roles(self):
        booking = self.create_booking()
        booking.status = 'APPROVED'
        booking.save(update_fields=['status'])
        self.assertEqual(Notification.objects.filter(title='Reservation approved', recipient=self.admin).count(), 1)
        self.assertEqual(Notification.objects.filter(title='Your reservation is approved', recipient=self.user).count(), 1)
        booking.start_datetime += timedelta(hours=1)
        booking.end_datetime += timedelta(hours=1)
        booking.save(update_fields=['start_datetime', 'end_datetime'])
        self.assertEqual(Notification.objects.filter(title='Reservation rescheduled', recipient=self.admin).count(), 1)
        self.assertEqual(Notification.objects.filter(title='Your schedule has changed', recipient=self.user).count(), 1)

    def test_request_copy_is_personal_for_owner_and_identifies_requester_for_admin(self):
        self.user.first_name = 'Yanz'
        self.user.last_name = 'Eusebio'
        self.user.save(update_fields=['first_name', 'last_name'])
        booking = self.create_booking()
        admin = Notification.objects.get(reservation=booking, recipient=self.admin)
        owner = Notification.objects.get(reservation=booking, recipient=self.user)
        self.assertEqual(admin.title, 'New reservation request')
        self.assertIn('Yanz Eusebio', admin.message)
        self.assertEqual(owner.title, 'Request submitted')
        self.assertIn('Awaiting administrator approval.', owner.message)
        self.assertNotIn('Yanz Eusebio', owner.message)
        for row in (admin, owner):
            self.assertIn('Meeting room', row.message)
            self.assertIn(f'#{booking.pk}', row.message)
            self.assertIn('PHT', row.message)
        for account, title in [(self.user, owner.title), (self.admin, admin.title)]:
            self.login_as(account)
            # The latest toast context must not depend on the inbox tab/page.
            data = self.client.get(reverse('notification_feed'), {'tab': 'all', 'page': 2}).json()
            self.assertEqual(data['items'], [])
            self.assertEqual(data['latest_unread']['title'], title)

    def test_all_statuses_have_role_specific_context_without_claiming_an_actor(self):
        from .notification_events import USER_COPY
        booking = self.create_booking()
        for status, _ in Reservation.STATUS_CHOICES:
            if status == 'PENDING':
                continue
            with self.subTest(status=status):
                booking.status = status
                booking.save(update_fields=['status'])
                admin = Notification.objects.filter(recipient=self.admin).first()
                owner = Notification.objects.filter(recipient=self.user).first()
                self.assertEqual(owner.title, USER_COPY[status][0])
                self.assertIn(USER_COPY[status][1], owner.message)
                self.assertIn(self.user.username, admin.message)
                self.assertNotEqual(admin.title, owner.title)
                self.assertNotIn('cancelled by', owner.message)

    def test_admin_owner_gets_one_personal_update_not_a_duplicate(self):
        booking = self.create_booking()
        booking.user = self.admin
        booking.save(update_fields=['user'])
        Notification.objects.all().delete()
        booking.status = 'APPROVED'
        booking.save(update_fields=['status'])
        notice = Notification.objects.get(reservation=booking)
        self.assertEqual(notice.recipient, self.admin)
        self.assertEqual(notice.title, 'Your reservation is approved')

    def test_unchanged_and_unsaved_dirty_values_do_not_notify(self):
        booking = self.create_booking()
        booking.save()
        booking.status = 'APPROVED'
        booking.save(update_fields=['purpose'])
        self.assertEqual(Notification.objects.count(), 2)

    def test_rolled_back_booking_does_not_leave_notifications(self):
        with self.assertRaises(ValueError):
            with transaction.atomic():
                self.create_booking()
                raise ValueError('rollback')
        self.assertFalse(Notification.objects.exists())

    def test_feed_is_private_and_links_match_roles(self):
        booking = self.create_booking()
        for user, route in [(self.user, 'reservation_detail_user'), (self.admin, 'reservation_detail_admin')]:
            self.login_as(user)
            response = self.client.get(reverse('notification_feed'))
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json()['unread_count'], 1)
            self.assertEqual(response.json()['items'][0]['url'], reverse(route, args=[booking.pk]))
            self.assertIn('no-store', response['Cache-Control'])
        self.login_as(self.other)
        self.assertEqual(self.client.get(reverse('notification_feed')).json()['items'], [])

    def test_read_scope_and_cutoff_preserve_new_arrivals(self):
        self.create_booking()
        self.login_as()
        first = Notification.objects.filter(recipient=self.user).first()
        foreign = Notification.objects.filter(recipient=self.admin).first()
        self.assertEqual(self.read({'id': foreign.pk}).json()['updated'], 0)
        later = Notification.objects.create(recipient=self.user, title='Later', message='New arrival')
        self.assertEqual(self.read({'through': first.pk}).json()['updated'], 1)
        later.refresh_from_db()
        self.assertIsNone(later.read_at)
        self.assertEqual(self.client.get(reverse('notification_feed'), {'tab': 'unread'}).json()['unread_count'], 1)
        self.assertEqual(self.read({'id': first.pk}).json()['updated'], 0)

    def test_pagination_and_unread_filter(self):
        Notification.objects.bulk_create([Notification(recipient=self.user, title=f'Item {i}', message='Update') for i in range(45)])
        self.login_as()
        data = self.client.get(reverse('notification_feed')).json()
        self.assertEqual(len(data['items']), 20)
        self.assertTrue(data['has_next'])
        last = self.client.get(reverse('notification_feed'), {'page': 3}).json()
        self.assertEqual(len(last['items']), 5)
        self.assertFalse(last['has_next'])
        self.read({'through': data['latest_id']})
        self.assertEqual(self.client.get(reverse('notification_feed'), {'tab': 'unread'}).json()['items'], [])
        self.assertEqual(len(self.client.get(reverse('notification_feed'), {'tab': 'all'}).json()['items']), 20)

    def test_login_methods_csrf_and_bad_input(self):
        self.assertEqual(self.client.get(reverse('notification_feed')).status_code, 302)
        self.login_as()
        self.assertEqual(self.client.get(reverse('notification_read')).status_code, 405)
        self.assertEqual(self.client.post(reverse('notification_feed')).status_code, 405)
        for body in ['bad', '[]', '{}', '{"id":true}', '{"id":-1}', '{"id":999999999999999999999}']:
            self.assertEqual(self.client.post(reverse('notification_read'), body, content_type='application/json').status_code, 400)
        secure = Client(enforce_csrf_checks=True)
        secure.force_login(self.user)
        self.assertEqual(secure.post(reverse('notification_read'), '{}', content_type='application/json').status_code, 403)

    def test_bell_is_shared_and_fields_are_escaped_in_javascript(self):
        for user, route in [(self.user, 'user_dashboard'), (self.admin, 'admin_dashboard')]:
            self.login_as(user)
            response = self.client.get(reverse(route))
            self.assertContains(response, 'data-notification-center', count=1)
            self.assertContains(response, 'notification-center.js')
            self.assertContains(response, 'notification-center.css')
