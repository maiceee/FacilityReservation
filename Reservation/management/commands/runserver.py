"""Keep local expiry running even when no browser is open.

Production deployments run the separate supervised --watch command instead.
"""
from threading import Event, Thread

from django.contrib.staticfiles.management.commands.runserver import Command as StaticRunserver

from Reservation.expiry import run_expiry_worker


class Command(StaticRunserver):
    def inner_run(self, *args, **options):
        stop = Event()
        worker = Thread(target=run_expiry_worker, args=(stop,), daemon=True, name='pending-reservation-expiry')
        worker.start()
        try:
            return super().inner_run(*args, **options)
        finally:
            stop.set()
            worker.join(timeout=2)
