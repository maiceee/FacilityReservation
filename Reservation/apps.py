from django.apps import AppConfig


class ReservationConfig(AppConfig):
    name = 'Reservation'

    def ready(self):
        from . import notification_events  # noqa: F401
