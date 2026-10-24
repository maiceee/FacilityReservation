"""Bounded directory queries and explicit, audited bulk status changes."""
from urllib.parse import urlencode

from django.contrib import messages
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Q
from django.http import Http404
from django.shortcuts import redirect
from django.urls import reverse
from django.views.decorators.http import require_POST

from .decorators import admin_required
from .models import Amenity, Facility, FacilityCategory
from .services import create_audit_log

DIRECTORIES = {
    'facility': (Facility, 'facility_list', 'FACILITY', 'Facility'),
    'category': (FacilityCategory, 'category_list', 'CATEGORY', 'Category'),
    'amenity': (Amenity, 'amenity_list', 'AMENITY', 'Amenity'),
}
PAGE_SIZE = 25


def directory_context(request, kind):
    model, _, _, _ = DIRECTORIES[kind]
    search = request.GET.get('search', '').strip()[:200]
    state = request.GET.get('state', 'active')
    if state not in ('active', 'inactive', 'all'):
        state = 'active'
    records = model.objects.all()
    if search:
        query = Q(name__icontains=search)
        if kind == 'facility':
            query |= Q(facility_code__icontains=search) | Q(location__icontains=search) | Q(category__name__icontains=search)
        records = records.filter(query)
    counts = {key: records.filter(is_active=value).count() for key, value in [('active', True), ('inactive', False)]}
    counts['all'] = counts['active'] + counts['inactive']
    if state != 'all':
        records = records.filter(is_active=state == 'active')
    if kind == 'facility':
        records = records.select_related('category')
    page = Paginator(records.order_by('name', 'pk'), PAGE_SIZE).get_page(request.GET.get('page'))
    return {
        'directory_kind': kind, 'search_query': search, 'directory_state': state,
        'page_obj': page,
        'directory_query': urlencode({'search': search, 'state': state}),
        'directory_tabs': [
            {'label': key.title(), 'count': counts[key], 'active': key == state,
             'url': '?' + urlencode({'search': search, 'state': key})}
            for key in ('active', 'inactive', 'all')
        ],
    }


@admin_required
@require_POST
def directory_bulk(request, kind):
    if kind not in DIRECTORIES:
        raise Http404
    model, route, audit_prefix, label = DIRECTORIES[kind]
    state = request.POST.get('state', 'active')
    if state not in ('active', 'inactive', 'all'):
        state = 'active'
    destination = reverse(route) + '?' + urlencode({
        'state': state, 'search': request.POST.get('search', '')[:200],
        'page': request.POST.get('page', '1')[:10],
    })
    selections = request.POST.getlist('selected')
    operation = request.POST.get('operation')
    expected = {}
    try:
        if not 1 <= len(selections) <= PAGE_SIZE or operation not in ('activate', 'deactivate'):
            raise ValueError
        for item in selections:
            raw_id, raw_state = item.split(':')
            if not raw_id.isdecimal() or len(raw_id) > 18 or raw_state not in ('0', '1'):
                raise ValueError
            record_id = int(raw_id)
            if record_id < 1 or record_id in expected:
                raise ValueError
            expected[record_id] = raw_state == '1'
    except (ValueError, TypeError):
        messages.error(request, 'Select 1–25 records and a valid status action. No records were changed.')
        return redirect(destination)
    target = operation == 'activate'
    with transaction.atomic():
        records = list(model.objects.select_for_update().filter(pk__in=expected).order_by('pk'))
        if len(records) != len(expected) or any(record.is_active != expected[record.pk] for record in records):
            messages.error(request, 'A selected record changed or no longer exists. Review the refreshed list and try again. Nothing was changed.')
            return redirect(destination)
        if kind == 'facility' and target and any(not record.category.is_active for record in records):
            messages.error(request, 'Activate the categories of the selected facilities first. Nothing was changed.')
            return redirect(destination)
        changed = 0
        for record in records:
            if record.is_active == target:
                continue
            record.is_active = target
            record.save(update_fields=['is_active'])
            create_audit_log(actor=request.user,
                action=f'{audit_prefix}_{"REACTIVATED" if target else "ARCHIVED"}',
                reference=f'{label} #{record.pk}', description=f'{record.name} (bulk status change)')
            changed += 1
    skipped = len(records) - changed
    result = f'{changed} record(s) {"activated" if target else "deactivated"}.'
    if skipped:
        result += f' {skipped} already had this status.'
    messages.success(request, result)
    return redirect(destination)
