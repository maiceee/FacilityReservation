"""Authenticated, recipient-scoped notification APIs; mutations require CSRF."""
import json

from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET, require_POST

from .models import Notification


@login_required
@never_cache
@require_GET
def notification_feed(request):
    inbox = Notification.objects.filter(recipient=request.user)
    try:
        page = max(1, min(int(request.GET.get('page', 1)), 100000))
    except (ValueError, TypeError):
        page = 1
    filtered = inbox.filter(read_at__isnull=True) if request.GET.get('tab') == 'unread' else inbox
    rows = list(filtered[(page - 1) * 20:page * 20 + 1])
    route = 'reservation_detail_admin' if request.user.role == 'ADMIN' else 'reservation_detail_user'
    newest_unread = inbox.filter(read_at__isnull=True).first()
    return JsonResponse({
        'unread_count': inbox.filter(read_at__isnull=True).count(),
        'latest_id': inbox.values_list('id', flat=True).first() or 0,
        'latest_unread': ({'id': newest_unread.pk, 'title': newest_unread.title}
                          if newest_unread else None),
        'page': page, 'has_next': len(rows) > 20,
        'items': [{
            'id': row.pk, 'title': row.title, 'message': row.message,
            'created_at': row.created_at.isoformat(), 'unread': row.read_at is None,
            'url': reverse(route, args=[row.reservation_id]) if row.reservation_id else '',
        } for row in rows[:20]],
    })


@login_required
@require_POST
def notification_read(request):
    try:
        data = json.loads(request.body)
        if not isinstance(data, dict):
            raise ValueError
        cutoff = data.get('through')
        item_id = data.get('id')
        value = cutoff if cutoff is not None else item_id
        if type(value) is not int or not 1 <= value <= 9223372036854775807:
            raise ValueError
    except (ValueError, TypeError, UnicodeDecodeError):
        return JsonResponse({'error': 'Choose a notification and try again.'}, status=400)
    rows = Notification.objects.filter(recipient=request.user, read_at__isnull=True)
    rows = rows.filter(pk__lte=value) if cutoff is not None else rows.filter(pk=value)
    count = rows.update(read_at=timezone.now())
    return JsonResponse({'updated': count})
