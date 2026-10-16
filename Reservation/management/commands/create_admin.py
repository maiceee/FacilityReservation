from getpass import getpass

from django.core.management.base import BaseCommand, CommandError
from Reservation.models import User


class Command(BaseCommand):
    help = 'Create an administrator account'

    def handle(self, *args, **options):
        username = input('Username: ').strip()
        email = input('Email: ').strip()
        first_name = input('First name: ').strip()
        last_name = input('Last name: ').strip()
        department = input('Department/Office: ').strip()
        contact_number = input('Contact number: ').strip()

        if User.objects.filter(username=username).exists():
            raise CommandError('Username already exists.')

        password = getpass('Password: ')
        confirm_password = getpass('Confirm password: ')

        if password != confirm_password:
            raise CommandError('Passwords do not match.')

        user = User.objects.create_user(
            username=username,
            email=email,
            first_name=first_name,
            last_name=last_name,
            department=department,
            contact_number=contact_number,
            password=password,
            role='ADMIN',
            is_staff=True,
            is_superuser=True,
        )

        self.stdout.write(
            self.style.SUCCESS(
                f'Admin account "{user.username}" created successfully.'
            )
        )