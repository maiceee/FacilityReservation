from threading import Event

from django.core.management.base import BaseCommand
from django.utils import timezone

from Reservation.expiry import expire_pending_reservations, run_expiry_worker
from Reservation.models import Reservation


class Command(BaseCommand):
    help = 'Cancel unapproved reservations whose scheduled start has been reached.'

    def add_arguments(self, parser):
        parser.add_argument('--watch', action='store_true', help='Keep checking every five seconds.')
        parser.add_argument('--dry-run', action='store_true', help='Count due requests without changing them.')

    def handle(self, *args, **options):
        if options['dry_run']:
            count = Reservation.objects.filter(status='PENDING', start_datetime__lte=timezone.now()).count()
            self.stdout.write(f'{count} pending requests are due; no changes made.')
        elif options['watch']:
            try:
                run_expiry_worker(Event())
            except KeyboardInterrupt:
                self.stdout.write('Expiry worker stopped.')
        else:
            total = 0
            while True:
                count = expire_pending_reservations()
                total += count
                if count < 100:
                    break
            self.stdout.write(f'Automatically cancelled {total} pending requests.')
