import os
from datetime import datetime, time, timedelta

from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from Reservation.models import (
    User,
    FacilityCategory,
    Amenity,
    Facility,
    FacilityAmenity,
    Reservation,
    ClosureBlock,
    EventRecord,
    SystemSetting,
)


class Command(BaseCommand):
    help = 'Creates repeatable fictional demo data for the facility reservation system.'

    PASSWORD_ENVIRONMENT_VARIABLE = 'DEMO_ACCOUNT_PASSWORD'

    def add_arguments(self, parser):
        parser.add_argument(
            '--password',
            help=(
                'Password for all fictional demo accounts. '
                'If omitted, DEMO_ACCOUNT_PASSWORD is required.'
            ),
        )

    def get_demo_password(self, options):
        password = options.get('password')

        if password is None:
            password = os.environ.get(
                self.PASSWORD_ENVIRONMENT_VARIABLE
            )

        if not password or not password.strip():
            raise CommandError(
                'Provide the demo account password with --password or '
                'the DEMO_ACCOUNT_PASSWORD environment variable.'
            )

        try:
            validate_password(password)
        except ValidationError as error:
            raise CommandError(
                'The demo account password does not meet the configured '
                f'password requirements: {" ".join(error.messages)}'
            ) from error

        return password

    def local_datetime(self, date_value, hour, minute=0):
        """
        Creates a timezone-aware datetime using the
        project's configured local timezone.
        """
        naive_datetime = datetime.combine(
            date_value,
            time(hour, minute)
        )

        return timezone.make_aware(
            naive_datetime,
            timezone.get_current_timezone()
        )

    @transaction.atomic
    def handle(self, *args, **options):
        demo_password = self.get_demo_password(options)

        self.stdout.write(
            self.style.WARNING(
                'Creating facility reservation demo data...'
            )
        )

        today = timezone.localdate()

        # =====================================================
        # SYSTEM SETTINGS
        # =====================================================

        settings_object = SystemSetting.objects.first()

        if settings_object is None:
            SystemSetting.objects.create(
                max_event_duration_hours=4,
                advance_booking_days=30
            )

        # =====================================================
        # DEMO ADMIN
        #
        # Separate from any existing administrator.
        # =====================================================

        demo_admin, _ = User.objects.get_or_create(
            username='demo_admin',
            defaults={
                'first_name': 'Adrian',
                'last_name': 'Reyes',
                'email': 'demo.admin@example.com',
                'role': 'ADMIN',
                'department': 'Campus Administration',
                'contact_number': '09000000001',
                'is_active': True,
                'is_staff': False,
                'is_superuser': False,
            }
        )

        demo_admin.first_name = 'Adrian'
        demo_admin.last_name = 'Reyes'
        demo_admin.email = 'demo.admin@example.com'
        demo_admin.role = 'ADMIN'
        demo_admin.department = 'Campus Administration'
        demo_admin.contact_number = '09000000001'
        demo_admin.is_active = True

        demo_admin.set_password(demo_password)

        demo_admin.save()

        # =====================================================
        # 8 FICTIONAL BASIC USERS
        # =====================================================

        demo_users_data = [
            (
                'demo_student01',
                'Lia',
                'Navarro',
                'College of Information Technology',
                '09000000011'
            ),
            (
                'demo_student02',
                'Marco',
                'Villanueva',
                'College of Engineering',
                '09000000012'
            ),
            (
                'demo_student03',
                'Nina',
                'Castillo',
                'College of Education',
                '09000000013'
            ),
            (
                'demo_student04',
                'Paolo',
                'Mendoza',
                'College of Business',
                '09000000014'
            ),
            (
                'demo_student05',
                'Sofia',
                'Ramos',
                'College of Arts and Sciences',
                '09000000015'
            ),
            (
                'demo_student06',
                'Ethan',
                'Flores',
                'College of Engineering',
                '09000000016'
            ),
            (
                'demo_student07',
                'Mika',
                'Torres',
                'College of Information Technology',
                '09000000017'
            ),
            (
                'demo_student08',
                'Noel',
                'Garcia',
                'College of Education',
                '09000000018'
            ),
        ]

        demo_users = []

        for (
            username,
            first_name,
            last_name,
            department,
            contact_number
        ) in demo_users_data:

            user, _ = User.objects.get_or_create(
                username=username,
                defaults={
                    'first_name': first_name,
                    'last_name': last_name,
                    'email': f'{username}@example.com',
                    'role': 'BASIC_USER',
                    'department': department,
                    'contact_number': contact_number,
                    'is_active': True,
                }
            )

            user.first_name = first_name
            user.last_name = last_name
            user.email = f'{username}@example.com'
            user.role = 'BASIC_USER'
            user.department = department
            user.contact_number = contact_number
            user.is_active = True

            user.set_password(demo_password)

            user.save()

            demo_users.append(user)

        # =====================================================
        # 3 FACILITY CATEGORIES
        # =====================================================

        category_data = [
            'Academic Spaces',
            'Meeting Spaces',
            'Activity Spaces',
        ]

        categories = {}

        for category_name in category_data:

            category, _ = FacilityCategory.objects.get_or_create(
                name=category_name,
                defaults={
                    'is_active': True
                }
            )

            category.is_active = True
            category.save(
                update_fields=['is_active']
            )

            categories[category_name] = category

        # =====================================================
        # 8 AMENITIES
        # =====================================================

        amenity_names = [
            'Projector',
            'Air Conditioning',
            'Sound System',
            'Whiteboard',
            'Wi-Fi',
            'Microphone',
            'Computer Units',
            'Stage',
        ]

        amenities = {}

        for amenity_name in amenity_names:

            amenity, _ = Amenity.objects.get_or_create(
                name=amenity_name,
                defaults={
                    'is_active': True
                }
            )

            amenity.is_active = True
            amenity.save(
                update_fields=['is_active']
            )

            amenities[amenity_name] = amenity

        # =====================================================
        # 6 FACILITIES
        # =====================================================

        facility_data = [
            {
                'code': 'DEMO-LAB-01',
                'name': 'Innovation Computer Laboratory',
                'category': 'Academic Spaces',
                'location': 'Technology Building - Room 201',
                'capacity': 40,
                'description': (
                    'Computer laboratory for academic '
                    'activities and workshops.'
                ),
                'amenities': [
                    'Projector',
                    'Air Conditioning',
                    'Wi-Fi',
                    'Computer Units',
                    'Whiteboard',
                ],
            },
            {
                'code': 'DEMO-LEC-01',
                'name': 'Multimedia Lecture Room',
                'category': 'Academic Spaces',
                'location': 'Academic Building - Room 305',
                'capacity': 60,
                'description': (
                    'Lecture room for presentations, '
                    'seminars, and classes.'
                ),
                'amenities': [
                    'Projector',
                    'Air Conditioning',
                    'Sound System',
                    'Whiteboard',
                    'Wi-Fi',
                ],
            },
            {
                'code': 'DEMO-CONF-01',
                'name': 'Conference Room A',
                'category': 'Meeting Spaces',
                'location': 'Administration Building - 2nd Floor',
                'capacity': 25,
                'description': (
                    'Conference room for meetings and '
                    'small group discussions.'
                ),
                'amenities': [
                    'Projector',
                    'Air Conditioning',
                    'Whiteboard',
                    'Wi-Fi',
                ],
            },
            {
                'code': 'DEMO-MTG-01',
                'name': 'Student Meeting Room',
                'category': 'Meeting Spaces',
                'location': 'Student Center - Room 102',
                'capacity': 20,
                'description': (
                    'Meeting space for recognized student '
                    'organizations and group activities.'
                ),
                'amenities': [
                    'Air Conditioning',
                    'Whiteboard',
                    'Wi-Fi',
                ],
            },
            {
                'code': 'DEMO-HALL-01',
                'name': 'University Activity Hall',
                'category': 'Activity Spaces',
                'location': 'Campus Activity Center',
                'capacity': 200,
                'description': (
                    'Large activity hall for university '
                    'programs and events.'
                ),
                'amenities': [
                    'Sound System',
                    'Microphone',
                    'Stage',
                    'Wi-Fi',
                ],
            },
            {
                'code': 'DEMO-STUDIO-01',
                'name': 'Creative Activity Studio',
                'category': 'Activity Spaces',
                'location': 'Student Center - Room 205',
                'capacity': 35,
                'description': (
                    'Flexible studio for workshops and '
                    'student activities.'
                ),
                'amenities': [
                    'Air Conditioning',
                    'Sound System',
                    'Whiteboard',
                    'Wi-Fi',
                ],
            },
        ]

        facilities = []

        for item in facility_data:

            facility, _ = Facility.objects.update_or_create(
                facility_code=item['code'],
                defaults={
                    'name': item['name'],
                    'category': categories[item['category']],
                    'location': item['location'],
                    'capacity': item['capacity'],
                    'description': item['description'],
                    'opening_time': time(8, 0),
                    'closing_time': time(20, 0),
                    'is_active': True,
                }
            )

            facilities.append(facility)

            for amenity_name in item['amenities']:

                FacilityAmenity.objects.get_or_create(
                    facility=facility,
                    amenity=amenities[amenity_name]
                )

        # =====================================================
        # REMOVE ONLY PREVIOUS DEMO TRANSACTION DATA
        #
        # This makes the command repeatable while preserving
        # manually created/non-demo records.
        # =====================================================

        demo_reservations = Reservation.objects.filter(
            event_name__startswith='DEMO - '
        )

        EventRecord.objects.filter(
            reservation__in=demo_reservations
        ).delete()

        demo_reservations.delete()

        ClosureBlock.objects.filter(
            reason__startswith='DEMO - '
        ).delete()

        # =====================================================
        # HELPER FOR RESERVATIONS
        # =====================================================

        def create_reservation(
            number,
            user,
            facility,
            day_offset,
            start_hour,
            end_hour,
            status,
            attendees,
            purpose,
            decision_reason=''
        ):
            reservation_date = (
                today + timedelta(days=day_offset)
            )

            start_datetime = self.local_datetime(
                reservation_date,
                start_hour
            )

            end_datetime = self.local_datetime(
                reservation_date,
                end_hour
            )

            decision_statuses = {
                'APPROVED',
                'REJECTED',
                'CHECKED_IN',
                'NO_SHOW',
                'COMPLETED',
            }

            reservation = Reservation.objects.create(
                user=user,
                facility=facility,
                event_name=(
                    f'DEMO - Campus Event {number:02d}'
                ),
                purpose=purpose,
                expected_attendees=attendees,
                start_datetime=start_datetime,
                end_datetime=end_datetime,
                status=status,
                decision_by=(
                    demo_admin
                    if status in decision_statuses
                    else None
                ),
                decision_at=(
                    timezone.now()
                    if status in decision_statuses
                    else None
                ),
                decision_reason=decision_reason,
            )

            return reservation

        # =====================================================
        # 24 RESERVATIONS
        #
        # Includes:
        # Pending
        # Approved
        # Rejected
        # Cancelled
        # Completed
        # No Show
        # Adjacent schedules
        # =====================================================

        reservations = []

        reservation_specs = [
            # Past completed/no-show/cancelled/rejected records
            (1, 0, 0, -12, 9, 11, 'COMPLETED', 25),
            (2, 1, 1, -11, 13, 15, 'COMPLETED', 35),
            (3, 2, 2, -10, 10, 12, 'COMPLETED', 15),
            (4, 3, 3, -9, 14, 16, 'COMPLETED', 12),
            (5, 4, 4, -8, 9, 12, 'COMPLETED', 80),
            (6, 5, 5, -7, 13, 15, 'COMPLETED', 25),

            # Two no-show event records
            (7, 6, 0, -6, 9, 11, 'NO_SHOW', 20),
            (8, 7, 1, -5, 14, 16, 'NO_SHOW', 30),

            (9, 0, 2, -4, 10, 12, 'CANCELLED', 15),
            (10, 1, 3, -3, 13, 15, 'REJECTED', 18),

            # Upcoming approved
            (11, 2, 0, 2, 9, 11, 'APPROVED', 30),
            (12, 3, 1, 2, 11, 13, 'APPROVED', 40),

            # Adjacent to reservation 11: 11:00 starts
            # exactly when reservation 11 ends.
            (13, 4, 0, 2, 11, 13, 'APPROVED', 25),

            (14, 5, 2, 3, 9, 11, 'APPROVED', 20),
            (15, 6, 3, 3, 13, 15, 'APPROVED', 15),
            (16, 7, 4, 4, 10, 13, 'APPROVED', 100),

            # Pending requests
            (17, 0, 5, 5, 9, 11, 'PENDING', 20),
            (18, 1, 1, 6, 13, 15, 'PENDING', 35),
            (19, 2, 2, 7, 10, 12, 'PENDING', 18),
            (20, 3, 3, 8, 14, 16, 'PENDING', 15),
            (21, 4, 4, 9, 9, 12, 'PENDING', 70),
            (22, 5, 5, 10, 13, 15, 'PENDING', 25),

            # Additional historical statuses
            (23, 6, 0, -2, 13, 15, 'REJECTED', 20),
            (24, 7, 1, -1, 9, 11, 'CANCELLED', 30),
        ]

        for spec in reservation_specs:

            (
                number,
                user_index,
                facility_index,
                day_offset,
                start_hour,
                end_hour,
                status,
                attendees
            ) = spec

            if status == 'REJECTED':
                decision_reason = (
                    'Schedule could not be accommodated.'
                )
            elif status in {
                'APPROVED',
                'COMPLETED',
                'NO_SHOW',
            }:
                decision_reason = (
                    'Approved for demonstration purposes.'
                )
            else:
                decision_reason = ''

            reservation = create_reservation(
                number=number,
                user=demo_users[user_index],
                facility=facilities[facility_index],
                day_offset=day_offset,
                start_hour=start_hour,
                end_hour=end_hour,
                status=status,
                attendees=attendees,
                purpose=(
                    'Fictional campus activity created '
                    'for system demonstration.'
                ),
                decision_reason=decision_reason
            )

            reservations.append(reservation)

        # =====================================================
        # 8 EVENT RECORDS
        #
        # Reservations 1-6 = Completed
        # Reservations 7-8 = No Show
        # =====================================================

        for reservation in reservations[:6]:

            checked_in_at = (
                reservation.start_datetime
                - timedelta(minutes=10)
            )

            actual_start = reservation.start_datetime

            actual_end = (
                reservation.end_datetime
                - timedelta(minutes=5)
            )

            EventRecord.objects.create(
                reservation=reservation,
                checked_in_at=checked_in_at,
                actual_start=actual_start,
                actual_end=actual_end,
                completed_at=actual_end,
                incident_notes=''
            )

        for reservation in reservations[6:8]:

            EventRecord.objects.create(
                reservation=reservation,
                no_show_at=(
                    reservation.end_datetime
                    + timedelta(minutes=15)
                ),
                incident_notes=(
                    'No check-in was recorded for this '
                    'fictional demonstration event.'
                )
            )

        # =====================================================
        # 5 CLOSURE BLOCKS
        # =====================================================

        closure_specs = [
            (
                facilities[0],
                12,
                14,
                17,
                'DEMO - Scheduled equipment maintenance'
            ),
            (
                facilities[1],
                13,
                8,
                12,
                'DEMO - Room inspection'
            ),
            (
                facilities[2],
                14,
                13,
                17,
                'DEMO - Air-conditioning maintenance'
            ),
            (
                facilities[4],
                15,
                8,
                12,
                'DEMO - Stage maintenance'
            ),
            (
                facilities[5],
                -15,
                8,
                10,
                'DEMO - Previous facility maintenance'
            ),
        ]

        for (
            facility,
            day_offset,
            start_hour,
            end_hour,
            reason
        ) in closure_specs:

            closure_date = (
                today + timedelta(days=day_offset)
            )

            ClosureBlock.objects.create(
                facility=facility,
                start_datetime=self.local_datetime(
                    closure_date,
                    start_hour
                ),
                end_datetime=self.local_datetime(
                    closure_date,
                    end_hour
                ),
                reason=reason,
                created_by=demo_admin,
                is_active=(day_offset >= 0),
                archived_at=(
                    None
                    if day_offset >= 0
                    else timezone.now()
                )
            )

        # =====================================================
        # RESULT
        # =====================================================

        self.stdout.write('')

        self.stdout.write(
            self.style.SUCCESS(
                'Demo data created successfully.'
            )
        )

        self.stdout.write(
            f'Categories: {len(category_data)}'
        )

        self.stdout.write(
            f'Facilities: {len(facility_data)}'
        )

        self.stdout.write(
            f'Amenities: {len(amenity_names)}'
        )

        self.stdout.write(
            f'Basic Users: {len(demo_users)}'
        )

        self.stdout.write(
            f'Reservations: {len(reservations)}'
        )

        self.stdout.write(
            'Closure Blocks: 5'
        )

        self.stdout.write(
            'Event Records: 8'
        )

        self.stdout.write('')
        self.stdout.write(
            'Demo administrator: demo_admin'
        )
        self.stdout.write(
            'Demo basic users: demo_student01 to demo_student08'
        )

        self.stdout.write(
            self.style.WARNING(
                'All demo identities and records are fictional.'
            )
        )
