from .expiry import expire_pending_reservations


class PendingExpiryMiddleware:
    """Refresh eligibility before rendering or handling an authenticated action."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.user.is_authenticated and request.user.is_active:
            expire_pending_reservations(user_id=None if request.user.role == 'ADMIN' else request.user.pk)
        return self.get_response(request)

    def process_view(self, request, view_func, view_args, view_kwargs):
        # A specific detail/action must be fresh even behind a large backlog.
        if ('reservation_id' in view_kwargs and request.user.is_authenticated
                and request.user.is_active):
            expire_pending_reservations(reservation_id=view_kwargs['reservation_id'],
                user_id=None if request.user.role == 'ADMIN' else request.user.pk)
