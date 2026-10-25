import csv
from urllib.parse import urlencode

from .directory import directory_context

from django.contrib import messages
from django.contrib.auth import logout
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Count, Q, Sum, F, ExpressionWrapper, DurationField
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_GET
from datetime import datetime, timedelta
from django.core.paginator import Paginator

from .decorators import admin_required, basic_user_required, workspace_editor
from .forms import (
    UserRegistrationForm,
    UserProfileForm,
    FacilityCategoryForm,
    AmenityForm,
    FacilityForm,
    ReservationRequestForm,
    ReservationDecisionForm,
    ReservationCancellationForm,
    ReservationRescheduleForm,
    ClosureBlockForm,
    IncidentNotesForm,
    SystemSettingForm,
)
from .models import (
    User,
    FacilityCategory,
    Amenity,
    Facility,
    Reservation,
    ClosureBlock,
    ReservationChange,
    EventRecord,
    AuditLog,
    SystemSetting,
)
from .services import (
    create_audit_log,
    create_reservation_request,
    approve_reservation,
    reject_reservation,
    cancel_reservation,
    cancel_reservation_by_admin,
    reschedule_reservation,
    check_in_reservation,
    complete_reservation,
    mark_no_show,
    archive_closure_block,
    get_system_settings,
)


# =========================================================
# QUERY FILTER VALIDATION
# =========================================================


def pagination_query(request):
    """Keep repeated filters while replacing only the current page number."""
    params = request.GET.copy()
    params.pop('page', None)
    return params.urlencode()


def parse_iso_date_filter(value):
    normalized_value = (value or '').strip()

    if not normalized_value:
        return '', None

    try:
        parsed_value = datetime.strptime(
            normalized_value,
            '%Y-%m-%d'
        ).date()
    except (TypeError, ValueError):
        return '', None

    return normalized_value, parsed_value


def parse_positive_id_filter(value):
    normalized_value = (value or '').strip()

    if not normalized_value:
        return '', None

    try:
        parsed_value = int(normalized_value)
    except (TypeError, ValueError):
        return '', None

    if parsed_value < 1 or parsed_value > 2147483647:
        return '', None

    return str(parsed_value), parsed_value


# =========================================================
# AUTHENTICATION
# =========================================================

def register(request):
    if request.user.is_authenticated:
        return redirect('dashboard_redirect')

    if request.method == 'POST':
        form = UserRegistrationForm(request.POST)

        if form.is_valid():
            with transaction.atomic():
                account = form.save()

                create_audit_log(
                    actor=account,
                    action='ACCOUNT_REGISTERED',
                    reference=f'User #{account.pk}',
                    description=(
                        f'Basic User account registered for '
                        f'{account.username}.'
                    )
                )

            messages.success(
                request,
                'Account created successfully. You may now sign in.'
            )

            return redirect('login')

    else:
        form = UserRegistrationForm()

    return render(
        request,
        'Reservation/registration/RegistrationForm.html',
        {
            'form': form
        }
    )


def dashboard_redirect(request):
    if not request.user.is_authenticated:
        return redirect('login')

    if not request.user.is_active:
        logout(request)
        return redirect('login')

    if request.user.role == 'ADMIN':
        return redirect('admin_dashboard')

    if request.user.role == 'BASIC_USER':
        return redirect('user_dashboard')

    logout(request)
    return redirect('login')


# =========================================================
# ADMIN DASHBOARD
# =========================================================

@admin_required
def admin_dashboard(request):
    now = timezone.now()

    # =====================================================
    # DASHBOARD CARDS
    # =====================================================

    totals = Reservation.objects.aggregate(
        pending=Count('pk', filter=Q(status='PENDING')),
        upcoming=Count('pk', filter=Q(status='APPROVED', start_datetime__gte=now)),
        completed=Count('pk', filter=Q(status='COMPLETED')),
    )
    pending_requests = totals['pending']
    approved_upcoming = totals['upcoming']
    completed_events = totals['completed']

    active_facilities = Facility.objects.filter(
        is_active=True
    ).count()

    # =====================================================
    # RECENT RESERVATIONS
    # =====================================================

    recent_reservations = (
        Reservation.objects
        .select_related(
            'user',
            'facility'
        )
        .order_by('-created_at')[:5]
    )

    # =====================================================
    # MONTHLY BOOKING CHART
    # Current month + previous 5 months
    # =====================================================

    current_month_start = now.date().replace(
        day=1
    )

    monthly_labels = []
    monthly_booking_data = []
    monthly_counts = {}

    for month_offset in range(5, -1, -1):

        year = current_month_start.year
        month = current_month_start.month - month_offset

        while month <= 0:
            month += 12
            year -= 1

        month_start = current_month_start.replace(
            year=year,
            month=month,
            day=1
        )

        if month == 12:
            next_month_start = month_start.replace(
                year=year + 1,
                month=1,
                day=1
            )
        else:
            next_month_start = month_start.replace(
                month=month + 1,
                day=1
            )

        # Match the local-date chart boundaries using index-friendly datetimes.
        month_start_at = timezone.make_aware(datetime.combine(month_start, datetime.min.time()))
        next_month_at = timezone.make_aware(datetime.combine(next_month_start, datetime.min.time()))
        monthly_counts[f'month_{month_offset}'] = Count('pk', filter=Q(
            start_datetime__gte=month_start_at, start_datetime__lt=next_month_at,
        ))

        monthly_labels.append(
            month_start.strftime('%b %Y')
        )

    counts = Reservation.objects.aggregate(**monthly_counts)
    monthly_booking_data = [counts[key] for key in monthly_counts]

    # =====================================================
    # FACILITY USAGE CHART
    # Count reservations that represent actual facility use
    # =====================================================

    facility_usage = (
        Facility.objects
        .annotate(
            usage_count=Count(
                'reservations',
                filter=Q(
                    reservations__status__in=[
                        'APPROVED',
                        'CHECKED_IN',
                        'COMPLETED',
                        'NO_SHOW',
                    ]
                )
            )
        )
        .order_by(
            '-usage_count',
            'name'
        )
    )

    facility_labels = []
    facility_usage_data = []

    for facility in facility_usage:

        facility_labels.append(
            facility.name
        )

        facility_usage_data.append(
            facility.usage_count
        )

    # =====================================================
    # TEMPLATE
    # =====================================================

    return render(
        request,
        'Reservation/admin/dashboard/AdminDashboard.html',
        {
            'pending_requests': pending_requests,
            'approved_upcoming': approved_upcoming,
            'completed_events': completed_events,
            'active_facilities': active_facilities,
            'recent_reservations': recent_reservations,

            'monthly_labels': monthly_labels,
            'monthly_booking_data': monthly_booking_data,

            'facility_labels': facility_labels,
            'facility_usage_data': facility_usage_data,
        }
    )


# =========================================================
# ADMIN A1 - USER MANAGEMENT
# =========================================================

@admin_required
def user_management(request):
    search_query = request.GET.get(
        'search',
        ''
    ).strip()

    users = User.objects.filter(
        role='BASIC_USER'
    )

    if search_query:
        users = users.filter(
            Q(username__icontains=search_query)
            | Q(first_name__icontains=search_query)
            | Q(last_name__icontains=search_query)
            | Q(email__icontains=search_query)
            | Q(department__icontains=search_query)
        )

    users = users.order_by(
        '-date_joined',
        '-pk'
    )
    page = Paginator(users, 25).get_page(request.GET.get('page'))

    return render(
        request,
        'Reservation/admin/users/UserManagement.html',
        {
            'users': page.object_list,
            'page_obj': page,
            'directory_query': pagination_query(request),
            'search_query': search_query,
        }
    )


@admin_required
def toggle_user_status(request, user_id):
    if request.method != 'POST':
        return redirect('user_management')

    account = get_object_or_404(
        User,
        pk=user_id,
        role='BASIC_USER'
    )

    account.is_active = not account.is_active

    account.save(
        update_fields=['is_active']
    )

    action = (
        'ACCOUNT_ACTIVATED'
        if account.is_active
        else 'ACCOUNT_DEACTIVATED'
    )

    create_audit_log(
        actor=request.user,
        action=action,
        reference=f'User #{account.pk}',
        description=(
            f'Account status changed for '
            f'{account.username}.'
        )
    )

    messages.success(
        request,
        'Account status updated successfully.'
    )

    return redirect('user_management')


@admin_required
def admin_user_detail(request, user_id):
    account = get_object_or_404(
        User,
        pk=user_id,
        role='BASIC_USER'
    )

    reservation_history = (
        Reservation.objects
        .filter(user=account)
        .select_related('facility')
        .order_by('-start_datetime')
    )

    return render(
        request,
        'Reservation/admin/users/UserDetail.html',
        {
            'account': account,
            'reservation_history': reservation_history,
        }
    )


# =========================================================
# ADMIN A2 - FACILITY CATEGORIES
# =========================================================

@admin_required
def category_list(request):
    context = directory_context(request, 'category')
    context['categories'] = context['page_obj']
    return render(request, 'Reservation/admin/facilities/CategoryList.html', context)


@admin_required
@workspace_editor('category_list')
def category_create(request):
    if request.method == 'POST':
        form = FacilityCategoryForm(
            request.POST
        )

        if form.is_valid():
            category = form.save()

            create_audit_log(
                actor=request.user,
                action='CATEGORY_CREATED',
                reference=f'Category #{category.pk}',
                description=category.name
            )

            messages.success(
                request,
                'Facility category created successfully.'
            )

            return redirect('category_list')

    else:
        form = FacilityCategoryForm()

    return render(
        request,
        'Reservation/admin/facilities/CategoryForm.html',
        {
            'form': form,
            'page_title': 'Add Facility Category',
        }
    )


@admin_required
@workspace_editor('category_list')
def category_update(request, category_id):
    category = get_object_or_404(
        FacilityCategory,
        pk=category_id
    )

    if request.method == 'POST':
        form = FacilityCategoryForm(
            request.POST,
            instance=category
        )

        if form.is_valid():
            category = form.save()

            create_audit_log(
                actor=request.user,
                action='CATEGORY_UPDATED',
                reference=f'Category #{category.pk}',
                description=category.name
            )

            messages.success(
                request,
                'Facility category updated successfully.'
            )

            return redirect('category_list')

    else:
        form = FacilityCategoryForm(
            instance=category
        )

    return render(
        request,
        'Reservation/admin/facilities/CategoryForm.html',
        {
            'form': form,
            'page_title': 'Update Facility Category',
        }
    )


@admin_required
def category_archive(request, category_id):
    if request.method != 'POST':
        return redirect('category_list')

    category = get_object_or_404(
        FacilityCategory,
        pk=category_id
    )

    category.is_active = False

    category.save(
        update_fields=['is_active']
    )

    create_audit_log(
        actor=request.user,
        action='CATEGORY_ARCHIVED',
        reference=f'Category #{category.pk}',
        description=category.name
    )

    messages.success(
        request,
        'Facility category archived.'
    )

    return redirect('category_list')


# =========================================================
# ADMIN A2 - AMENITIES
# =========================================================

@admin_required
def amenity_list(request):
    context = directory_context(request, 'amenity')
    context['amenities'] = context['page_obj']
    return render(request, 'Reservation/admin/facilities/AmenityList.html', context)


@admin_required
@workspace_editor('amenity_list')
def amenity_create(request):
    if request.method == 'POST':
        form = AmenityForm(
            request.POST
        )

        if form.is_valid():
            amenity = form.save()

            create_audit_log(
                actor=request.user,
                action='AMENITY_CREATED',
                reference=f'Amenity #{amenity.pk}',
                description=amenity.name
            )

            messages.success(
                request,
                'Amenity created successfully.'
            )

            return redirect('amenity_list')

    else:
        form = AmenityForm()

    return render(
        request,
        'Reservation/admin/facilities/AmenityForm.html',
        {
            'form': form,
            'page_title': 'Add Amenity',
        }
    )


@admin_required
@workspace_editor('amenity_list')
def amenity_update(request, amenity_id):
    amenity = get_object_or_404(
        Amenity,
        pk=amenity_id
    )

    if request.method == 'POST':
        form = AmenityForm(
            request.POST,
            instance=amenity
        )

        if form.is_valid():
            amenity = form.save()

            create_audit_log(
                actor=request.user,
                action='AMENITY_UPDATED',
                reference=f'Amenity #{amenity.pk}',
                description=amenity.name
            )

            messages.success(
                request,
                'Amenity updated successfully.'
            )

            return redirect('amenity_list')

    else:
        form = AmenityForm(
            instance=amenity
        )

    return render(
        request,
        'Reservation/admin/facilities/AmenityForm.html',
        {
            'form': form,
            'page_title': 'Update Amenity',
        }
    )


@admin_required
def amenity_archive(request, amenity_id):
    if request.method != 'POST':
        return redirect('amenity_list')

    amenity = get_object_or_404(
        Amenity,
        pk=amenity_id
    )

    amenity.is_active = False

    amenity.save(
        update_fields=['is_active']
    )

    create_audit_log(
        actor=request.user,
        action='AMENITY_ARCHIVED',
        reference=f'Amenity #{amenity.pk}',
        description=amenity.name
    )

    messages.success(
        request,
        'Amenity archived.'
    )

    return redirect('amenity_list')


# =========================================================
# ADMIN A2 - FACILITIES
# =========================================================

@admin_required
def facility_list(request):
    context = directory_context(request, 'facility')
    context['facilities'] = context['page_obj']
    return render(request, 'Reservation/admin/facilities/FacilityList.html', context)


@admin_required
@require_GET
def facility_code_availability(request):
    facility_code = (
        request.GET.get('facility_code') or ''
    ).strip().upper()
    _, facility_id = parse_positive_id_filter(
        request.GET.get('exclude_facility')
    )

    duplicate_query = Facility.objects.none()

    if facility_code:
        duplicate_query = Facility.objects.filter(
            facility_code__iexact=facility_code
        )

        if facility_id is not None:
            duplicate_query = duplicate_query.exclude(pk=facility_id)

    return JsonResponse(
        {
            'exists': duplicate_query.exists(),
            'normalized_code': facility_code,
        }
    )


@admin_required
@workspace_editor('facility_list')
def facility_create(request):
    if request.method == 'POST':
        form = FacilityForm(
            request.POST
        )

        if form.is_valid():
            facility = form.save()

            create_audit_log(
                actor=request.user,
                action='FACILITY_CREATED',
                reference=f'Facility #{facility.pk}',
                description=facility.name
            )

            messages.success(
                request,
                'Facility created successfully.'
            )

            return redirect('facility_list')

    else:
        form = FacilityForm()

    return render(
        request,
        'Reservation/admin/facilities/FacilityForm.html',
        {
            'form': form,
            'page_title': 'Add Facility',
        }
    )


@admin_required
@workspace_editor('facility_list')
def facility_update(request, facility_id):
    facility = get_object_or_404(
        Facility,
        pk=facility_id
    )

    if request.method == 'POST':
        form = FacilityForm(
            request.POST,
            instance=facility
        )

        if form.is_valid():
            facility = form.save()

            create_audit_log(
                actor=request.user,
                action='FACILITY_UPDATED',
                reference=f'Facility #{facility.pk}',
                description=facility.name
            )

            messages.success(
                request,
                'Facility updated successfully.'
            )

            return redirect('facility_list')

    else:
        form = FacilityForm(
            instance=facility
        )

    return render(
        request,
        'Reservation/admin/facilities/FacilityForm.html',
        {
            'form': form,
            'page_title': 'Update Facility',
        }
    )


@admin_required
def facility_archive(request, facility_id):
    if request.method != 'POST':
        return redirect('facility_list')

    facility = get_object_or_404(
        Facility,
        pk=facility_id
    )

    facility.is_active = False

    facility.save(
        update_fields=['is_active']
    )

    create_audit_log(
        actor=request.user,
        action='FACILITY_ARCHIVED',
        reference=f'Facility #{facility.pk}',
        description=facility.name
    )

    messages.success(
        request,
        'Facility archived successfully.'
    )

    return redirect('facility_list')


# =========================================================
# ADMIN A3 - RESERVATION REVIEW
# =========================================================

@admin_required
def reservation_queue(request):
    search_query = request.GET.get(
        'search',
        ''
    ).strip()

    status_filter = request.GET.get(
        'status',
        ''
    ).strip()

    facility_filter, facility_id = parse_positive_id_filter(
        request.GET.get('facility', '')
    )

    date_filter, reservation_date = parse_iso_date_filter(
        request.GET.get('date', '')
    )

    reservations = (
        Reservation.objects
        .select_related(
            'user',
            'facility'
        )
    )

    if search_query:
        reservations = reservations.filter(
            Q(event_name__icontains=search_query)
            | Q(user__username__icontains=search_query)
            | Q(user__first_name__icontains=search_query)
            | Q(user__last_name__icontains=search_query)
        )

    if status_filter:
        reservations = reservations.filter(
            status=status_filter
        )

    if facility_id is not None:
        reservations = reservations.filter(
            facility_id=facility_id
        )

    if reservation_date is not None:
        reservations = reservations.filter(
            start_datetime__date=reservation_date
        )

    reservations = reservations.order_by(
        'start_datetime'
    )

    paginator = Paginator(
        reservations,
        10
    )

    page_number = request.GET.get(
        'page'
    )

    page_obj = paginator.get_page(
        page_number
    )

    facilities = Facility.objects.order_by(
        'name'
    )

    return render(
        request,
        'Reservation/admin/reservations/ReservationQueue.html',
        {
            'reservations': page_obj,
            'page_obj': page_obj,
            'facilities': facilities,
            'search_query': search_query,
            'status_filter': status_filter,
            'facility_filter': facility_filter,
            'date_filter': date_filter,
            'status_choices': Reservation.STATUS_CHOICES,
        }
    )


@admin_required
def reservation_detail_admin(request, reservation_id):
    reservation = get_object_or_404(
        Reservation.objects.select_related(
            'user',
            'facility',
            'decision_by'
        ),
        pk=reservation_id
    )

    changes = (
        ReservationChange.objects
        .filter(reservation=reservation)
        .select_related('changed_by')
        .order_by('-changed_at')
    )

    event_record = EventRecord.objects.filter(
        reservation=reservation
    ).first()

    return render(
        request,
        'Reservation/admin/reservations/ReservationDetail.html',
        {
            'reservation': reservation,
            'changes': changes,
            'event_record': event_record,
        }
    )


@admin_required
def reservation_approve(request, reservation_id):
    if request.method != 'POST':
        return redirect(
            'reservation_detail_admin',
            reservation_id=reservation_id
        )

    form = ReservationDecisionForm(
        request.POST
    )

    if form.is_valid():
        try:
            approve_reservation(
                reservation_id=reservation_id,
                admin_user=request.user,
                reason=form.cleaned_data[
                    'decision_reason'
                ]
            )

            messages.success(
                request,
                'Reservation approved successfully.'
            )

        except ValidationError as error:
            messages.error(
                request,
                ' '.join(error.messages)
            )
    else:
        messages.error(
            request,
            'An approval reason is required.'
        )

    return redirect(
        'reservation_detail_admin',
        reservation_id=reservation_id
    )


@admin_required
def reservation_reject(request, reservation_id):
    if request.method != 'POST':
        return redirect(
            'reservation_detail_admin',
            reservation_id=reservation_id
        )

    form = ReservationDecisionForm(
        request.POST
    )

    if form.is_valid():
        try:
            reject_reservation(
                reservation_id=reservation_id,
                admin_user=request.user,
                reason=form.cleaned_data[
                    'decision_reason'
                ]
            )

            messages.success(
                request,
                'Reservation rejected.'
            )

        except ValidationError as error:
            messages.error(
                request,
                ' '.join(error.messages)
            )
    else:
        messages.error(
            request,
            'A rejection reason is required.'
        )

    return redirect(
        'reservation_detail_admin',
        reservation_id=reservation_id
    )


@admin_required
def reservation_cancel_admin(request, reservation_id):
    get_object_or_404(
        Reservation,
        pk=reservation_id
    )

    if request.method != 'POST':
        return redirect(
            'reservation_detail_admin',
            reservation_id=reservation_id
        )

    form = ReservationCancellationForm(
        request.POST
    )

    if not form.is_valid():
        messages.error(
            request,
            'A cancellation reason is required.'
        )
    else:
        try:
            cancel_reservation_by_admin(
                reservation_id=reservation_id,
                admin_user=request.user,
                reason=form.cleaned_data['reason']
            )

            messages.success(
                request,
                'Reservation cancelled successfully.'
            )

        except ValidationError as error:
            messages.error(
                request,
                ' '.join(error.messages)
            )

    return redirect(
        'reservation_detail_admin',
        reservation_id=reservation_id
    )


# =========================================================
# ADMIN A4 - CALENDAR
# =========================================================

@admin_required
def admin_calendar(request):
    view_mode = request.GET.get('view', 'week').strip().lower()
    date_value = request.GET.get('date', '').strip()
    facility_value, facility_id = parse_positive_id_filter(
        request.GET.get('facility')
    )

    if view_mode not in ['day', 'week']:
        view_mode = 'week'

    try:
        if date_value:
            selected_date = datetime.strptime(
                date_value,
                '%Y-%m-%d'
            ).date()
        else:
            selected_date = timezone.localdate()

    except ValueError:
        selected_date = timezone.localdate()

    if view_mode == 'day':
        range_start = selected_date
        range_end = selected_date

        previous_date = selected_date - timedelta(days=1)
        next_date = selected_date + timedelta(days=1)

    else:
        range_start = (
            selected_date - timedelta(days=selected_date.weekday())
        )
        range_end = range_start + timedelta(days=6)

        previous_date = selected_date - timedelta(days=7)
        next_date = selected_date + timedelta(days=7)

    facilities = Facility.objects.order_by(
        'name'
    )

    reservations = (
        Reservation.objects
        .filter(
            start_datetime__date__gte=range_start,
            start_datetime__date__lte=range_end,
        )
        .exclude(
            status__in=[
                'REJECTED',
                'CANCELLED',
            ]
        )
        .select_related(
            'facility',
            'user'
        )
        .order_by(
            'start_datetime'
        )
    )

    if facility_id is not None:
        reservations = reservations.filter(
            facility_id=facility_id
        )

    closures = (
        ClosureBlock.objects
        .filter(
            is_active=True,
            start_datetime__date__lte=range_end,
            end_datetime__date__gte=range_start,
        )
        .select_related(
            'facility'
        )
        .order_by(
            'start_datetime'
        )
    )

    if facility_id is not None:
        closures = closures.filter(
            facility_id=facility_id
        )

    calendar_days = []
    current_date = range_start

    while current_date <= range_end:

        day_reservations = []

        for reservation in reservations:
            if (
                timezone.localtime(
                    reservation.start_datetime
                ).date()
                == current_date
            ):
                day_reservations.append(
                    reservation
                )

        day_closures = []

        for closure in closures:

            closure_start_date = timezone.localtime(
                closure.start_datetime
            ).date()

            closure_end_date = timezone.localtime(
                closure.end_datetime
            ).date()

            if (
                closure_start_date
                <= current_date
                <= closure_end_date
            ):
                day_closures.append(
                    closure
                )

        calendar_days.append({
            'date': current_date,
            'reservations': day_reservations,
            'closures': day_closures,
        })

        current_date += timedelta(days=1)

    context = {
        'view_mode': view_mode,
        'selected_date': selected_date,
        'range_start': range_start,
        'range_end': range_end,
        'previous_date': previous_date,
        'next_date': next_date,
        'facilities': facilities,
        'facility_filter': facility_value,
        'calendar_days': calendar_days,
    }

    return render(
        request,
        'Reservation/admin/reservations/AdminCalendar.html',
        context
    )


# =========================================================
# ADMIN A4 - RESCHEDULING
# =========================================================

@admin_required
@workspace_editor('reservation_detail_admin', workspace_args=('reservation_id',))
def reservation_reschedule(request, reservation_id):
    reservation = get_object_or_404(
        Reservation,
        pk=reservation_id
    )

    if request.method == 'POST':
        form = ReservationRescheduleForm(
            request.POST
        )

        if form.is_valid():
            try:
                reschedule_reservation(
                    reservation_id=reservation.pk,
                    admin_user=request.user,
                    new_start_datetime=form.cleaned_data[
                        'start_datetime'
                    ],
                    new_end_datetime=form.cleaned_data[
                        'end_datetime'
                    ],
                    reason=form.cleaned_data[
                        'reason'
                    ]
                )

                messages.success(
                    request,
                    'Reservation rescheduled successfully.'
                )

                return redirect(
                    'reservation_detail_admin',
                    reservation_id=reservation.pk
                )

            except ValidationError as error:
                form.add_error(
                    None,
                    ' '.join(error.messages)
                )

    else:
        form = ReservationRescheduleForm(
            initial={
                'start_datetime': reservation.start_datetime,
                'end_datetime': reservation.end_datetime,
            }
        )

    return render(
        request,
        'Reservation/admin/reservations/ReservationReschedule.html',
        {
            'reservation': reservation,
            'form': form,
        }
    )


# =========================================================
# ADMIN A5 - EVENT OPERATIONS
# =========================================================

@admin_required
def reservation_check_in(request, reservation_id):
    if request.method == 'POST':
        try:
            check_in_reservation(
                reservation_id,
                request.user
            )

            messages.success(
                request,
                'Event checked in successfully.'
            )

        except ValidationError as error:
            messages.error(
                request,
                ' '.join(error.messages)
            )

    return redirect(
        'reservation_detail_admin',
        reservation_id=reservation_id
    )


@admin_required
def reservation_complete(request, reservation_id):
    if request.method == 'POST':
        form = IncidentNotesForm(
            request.POST
        )

        if form.is_valid():
            try:
                complete_reservation(
                    reservation_id,
                    request.user,
                    form.cleaned_data[
                        'incident_notes'
                    ]
                )

                messages.success(
                    request,
                    'Event completed successfully.'
                )

            except ValidationError as error:
                messages.error(
                    request,
                    ' '.join(error.messages)
                )

    return redirect(
        'reservation_detail_admin',
        reservation_id=reservation_id
    )


@admin_required
def reservation_no_show(request, reservation_id):
    if request.method == 'POST':
        try:
            mark_no_show(
                reservation_id,
                request.user
            )

            messages.success(
                request,
                'Reservation marked as no-show.'
            )

        except ValidationError as error:
            messages.error(
                request,
                ' '.join(error.messages)
            )

    return redirect(
        'reservation_detail_admin',
        reservation_id=reservation_id
    )


# =========================================================
# ADMIN A5 - PRINTABLE DOCUMENTS
# =========================================================

@admin_required
def reservation_slip(request, reservation_id):
    reservation = get_object_or_404(
        Reservation.objects.select_related(
            'user',
            'facility',
            'facility__category',
            'decision_by',
        ),
        pk=reservation_id
    )

    allowed_statuses = [
        'APPROVED',
        'CHECKED_IN',
        'COMPLETED',
        'NO_SHOW',
    ]

    if reservation.status not in allowed_statuses:
        messages.error(
            request,
            'A reservation slip is available only for '
            'approved or processed reservations.'
        )

        return redirect(
            'reservation_detail_admin',
            reservation_id=reservation.pk
        )

    return render(
        request,
        'Reservation/admin/reservations/ReservationSlip.html',
        {
            'reservation': reservation,
        }
    )


@admin_required
def completion_summary(request, reservation_id):
    reservation = get_object_or_404(
        Reservation.objects.select_related(
            'user',
            'facility',
            'facility__category',
            'decision_by',
        ),
        pk=reservation_id
    )

    if reservation.status != 'COMPLETED':
        messages.error(
            request,
            'Completion summary is available only '
            'for completed events.'
        )

        return redirect(
            'reservation_detail_admin',
            reservation_id=reservation.pk
        )

    event_record = get_object_or_404(
        EventRecord,
        reservation=reservation
    )

    return render(
        request,
        'Reservation/admin/reservations/CompletionSummary.html',
        {
            'reservation': reservation,
            'event_record': event_record,
        }
    )


# =========================================================
# ADMIN A6 - CLOSURES
# =========================================================

@admin_required
def closure_list(request):
    closures = (
        ClosureBlock.objects
        .select_related(
            'facility',
            'created_by'
        )
        .order_by('-start_datetime', '-pk')
    )

    page = Paginator(closures, 25).get_page(request.GET.get('page'))
    return render(
        request,
        'Reservation/admin/closures/ClosureList.html',
        {
            'closures': page.object_list,
            'page_obj': page,
            'directory_query': pagination_query(request),
        }
    )


@admin_required
@workspace_editor('closure_list')
def closure_create(request):
    conflicting_reservations = Reservation.objects.none()

    if request.method == 'POST':
        form = ClosureBlockForm(
            request.POST
        )

        if form.is_valid():
            facility = form.cleaned_data[
                'facility'
            ]

            start_datetime = form.cleaned_data[
                'start_datetime'
            ]

            end_datetime = form.cleaned_data[
                'end_datetime'
            ]

            conflicting_reservations = (
                Reservation.objects
                .filter(
                    facility=facility,
                    status__in=[
                        'APPROVED',
                        'CHECKED_IN',
                    ],
                    start_datetime__lt=end_datetime,
                    end_datetime__gt=start_datetime
                )
                .select_related(
                    'user',
                    'facility'
                )
                .order_by(
                    'start_datetime'
                )
            )

            if conflicting_reservations.exists():

                form.add_error(
                    None,
                    'The closure cannot be created because '
                    'it conflicts with an existing Approved '
                    'or Checked In reservation. Review the '
                    'conflicting reservation below and '
                    'reschedule or resolve it first.'
                )

            else:
                closure = form.save(
                    commit=False
                )

                closure.created_by = request.user

                closure.save()

                create_audit_log(
                    actor=request.user,
                    action='CLOSURE_CREATED',
                    reference=f'Closure #{closure.pk}',
                    description=(
                        f'{closure.facility.name}: '
                        f'{closure.reason}'
                    )
                )

                messages.success(
                    request,
                    'Closure created successfully.'
                )

                return redirect(
                    'closure_list'
                )

    else:
        form = ClosureBlockForm()

    return render(
        request,
        'Reservation/admin/closures/ClosureForm.html',
        {
            'form': form,
            'conflicting_reservations': conflicting_reservations,
        }
    )


@admin_required
def closure_archive(request, closure_id):
    if request.method != 'POST':
        return redirect('closure_list')

    get_object_or_404(
        ClosureBlock,
        pk=closure_id
    )

    try:
        archive_closure_block(
            closure_id=closure_id,
            admin_user=request.user
        )

        messages.success(
            request,
            'Closure archived successfully.'
        )

    except ValidationError as error:
        messages.error(
            request,
            ' '.join(error.messages)
        )

    return redirect('closure_list')


# =========================================================
# ADMIN A7 - REPORTS
# =========================================================

def report_facility_ids(request):
    # An invalid supplied selection yields no records, never an unfiltered export.
    supplied = request.GET.getlist('facility')
    if not supplied:
        return None
    return sorted({int(value) for value in supplied if value.isdecimal() and len(value) <= 18 and int(value) > 0})


def build_facility_usage_report(
    start_date=None,
    end_date=None,
    facility_ids=None
):
    facilities = Facility.objects.order_by(
        'name'
    )

    if facility_ids is not None:
        facilities = facilities.filter(pk__in=facility_ids)

    booking_filter = Q(reservations__status__in=['APPROVED', 'CHECKED_IN', 'COMPLETED', 'NO_SHOW'])
    if start_date is not None:
        booking_filter &= Q(reservations__start_datetime__date__gte=start_date)
    if end_date is not None:
        booking_filter &= Q(reservations__start_datetime__date__lte=end_date)
    duration = ExpressionWrapper(F('reservations__end_datetime') - F('reservations__start_datetime'), output_field=DurationField())
    facilities = facilities.annotate(
        report_completed=Count('reservations', filter=booking_filter & Q(reservations__status='COMPLETED')),
        report_duration=Sum(duration, filter=booking_filter),
    )
    rows = []
    total = 0
    for facility in facilities:
        hours = round(facility.report_duration.total_seconds() / 3600, 2) if facility.report_duration else 0
        rows.append({'facility': facility, 'completed_events': facility.report_completed, 'booked_hours': hours})
        total += hours
    return rows, round(total, 2)


@admin_required
def reports(request):
    selected_facilities = report_facility_ids(request)
    start_date, parsed_start_date = parse_iso_date_filter(
        request.GET.get('start_date', '')
    )

    end_date, parsed_end_date = parse_iso_date_filter(
        request.GET.get('end_date', '')
    )

    reservations = (
        Reservation.objects
        .select_related(
            'facility',
            'user'
        )
        .order_by('-start_datetime', '-pk')
    )

    if selected_facilities is not None:
        reservations = reservations.filter(facility_id__in=selected_facilities)

    if parsed_start_date is not None:
        reservations = reservations.filter(
            start_datetime__date__gte=parsed_start_date
        )

    if parsed_end_date is not None:
        reservations = reservations.filter(
            start_datetime__date__lte=parsed_end_date
        )

    report_counts = reservations.aggregate(
        total=Count('pk'),
        completed=Count('pk', filter=Q(status='COMPLETED')),
    )
    total_reservations = report_counts['total']
    completed_reservations = report_counts['completed']

    facility_usage_rows, total_booked_hours = (
        build_facility_usage_report(
            start_date=parsed_start_date,
            end_date=parsed_end_date,
            facility_ids=selected_facilities
        )
    )
    page = Paginator(reservations, 25).get_page(request.GET.get('page'))

    return render(
        request,
        'Reservation/admin/reports/Reports.html',
        {
            'reservations': page.object_list,
            'page_obj': page,
            'directory_query': pagination_query(request),
            'report_facilities': Facility.objects.order_by('name', 'pk'),
            'selected_facilities': selected_facilities or [],
            'facility_query': urlencode({'facility': selected_facilities or []}, doseq=True),
            'facility_usage_rows': facility_usage_rows,

            'start_date': start_date,
            'end_date': end_date,

            'total_reservations': total_reservations,
            'completed_reservations': completed_reservations,
            'total_booked_hours': total_booked_hours,
        }
    )


@admin_required
def export_reservations_csv(request):
    selected_facilities = report_facility_ids(request)
    _, parsed_start_date = parse_iso_date_filter(
        request.GET.get('start_date', '')
    )

    _, parsed_end_date = parse_iso_date_filter(
        request.GET.get('end_date', '')
    )

    reservations = (
        Reservation.objects
        .select_related(
            'facility',
            'user'
        )
        .order_by('start_datetime')
    )

    if selected_facilities is not None:
        reservations = reservations.filter(facility_id__in=selected_facilities)

    if parsed_start_date is not None:
        reservations = reservations.filter(
            start_datetime__date__gte=parsed_start_date
        )

    if parsed_end_date is not None:
        reservations = reservations.filter(
            start_datetime__date__lte=parsed_end_date
        )

    response = HttpResponse(
        content_type='text/csv'
    )

    response[
        'Content-Disposition'
    ] = (
        'attachment; '
        'filename="reservation_report.csv"'
    )

    writer = csv.writer(response)

    writer.writerow([
        'Reservation ID',
        'User',
        'Facility',
        'Event',
        'Participants',
        'Start',
        'End',
        'Status',
    ])

    for reservation in reservations:
        writer.writerow([
            reservation.pk,
            reservation.user.username,
            reservation.facility.name,
            reservation.event_name,
            reservation.expected_attendees,
            timezone.localtime(
                reservation.start_datetime
            ).strftime('%Y-%m-%d %H:%M'),
            timezone.localtime(
                reservation.end_datetime
            ).strftime('%Y-%m-%d %H:%M'),
            reservation.get_status_display(),
        ])

    return response


@admin_required
def export_facility_usage_csv(request):
    selected_facilities = report_facility_ids(request)
    _, parsed_start_date = parse_iso_date_filter(
        request.GET.get('start_date', '')
    )

    _, parsed_end_date = parse_iso_date_filter(
        request.GET.get('end_date', '')
    )

    facility_usage_rows, _ = build_facility_usage_report(
        start_date=parsed_start_date,
        end_date=parsed_end_date,
            facility_ids=selected_facilities
    )

    response = HttpResponse(
        content_type='text/csv'
    )
    response['Content-Disposition'] = (
        'attachment; '
        'filename="facility_utilization_report.csv"'
    )

    writer = csv.writer(response)
    writer.writerow([
        'Facility Code',
        'Facility',
        'Completed Events',
        'Booked Hours',
    ])

    for row in facility_usage_rows:
        writer.writerow([
            row['facility'].facility_code,
            row['facility'].name,
            row['completed_events'],
            f"{row['booked_hours']:.2f}",
        ])

    return response


# =========================================================
# ADMIN A8 - AUDIT LOGS
# =========================================================

@admin_required
def audit_logs(request):
    search_query = request.GET.get(
        'search',
        ''
    ).strip()

    logs = AuditLog.objects.select_related(
        'actor'
    )

    if search_query:
        logs = logs.filter(
            Q(action__icontains=search_query)
            | Q(reference__icontains=search_query)
            | Q(description__icontains=search_query)
            | Q(actor__username__icontains=search_query)
        )

    logs = logs.order_by(
        '-timestamp', '-pk'
    )
    page = Paginator(logs, 25).get_page(request.GET.get('page'))

    return render(
        request,
        'Reservation/admin/reports/AuditLogs.html',
        {
            'logs': page.object_list,
            'page_obj': page,
            'directory_query': pagination_query(request),
            'search_query': search_query,
        }
    )


# =========================================================
# ADMIN A8 - SYSTEM SETTINGS
# =========================================================

@admin_required
@workspace_editor('admin_dashboard')
def system_settings(request):
    settings_object = get_system_settings()

    if request.method == 'POST':
        form = SystemSettingForm(
            request.POST,
            instance=settings_object
        )

        if form.is_valid():
            settings_object = form.save(
                commit=False
            )

            settings_object.updated_by = (
                request.user
            )

            settings_object.save()

            create_audit_log(
                actor=request.user,
                action='SETTINGS_UPDATED',
                reference='Booking Settings',
                description=(
                    'Maximum event duration and '
                    'advance booking window updated.'
                )
            )

            messages.success(
                request,
                'Booking settings updated successfully.'
            )

            return redirect('system_settings')

    else:
        form = SystemSettingForm(
            instance=settings_object
        )

    return render(
        request,
        'Reservation/admin/reports/SystemSettings.html',
        {
            'form': form
        }
    )


# =========================================================
# BASIC USER - DASHBOARD
# =========================================================

@basic_user_required
def user_dashboard(request):
    now = timezone.now()
    confirmed = (
        Reservation.objects
        .filter(
            user=request.user,
            status__in=['APPROVED', 'CHECKED_IN'],
            end_datetime__gt=now,
        )
        .select_related('facility')
        .order_by('start_datetime', 'pk')
    )
    ongoing = confirmed.filter(start_datetime__lte=now).first()
    upcoming = list(confirmed.filter(start_datetime__gt=now)[:5])
    highlighted = ongoing or (upcoming[0] if upcoming else None)

    return render(
        request,
        'Reservation/user/UserDashboard.html',
        {
            'upcoming_reservations': upcoming,
            'highlighted_reservation': highlighted,
            'has_ongoing_reservation': ongoing is not None,
            'pending_request_count': Reservation.objects.filter(user=request.user, status='PENDING').count(),
        }
    )


# =========================================================
# BASIC USER U1 - PROFILE
# =========================================================

@basic_user_required
@workspace_editor('user_dashboard')
def user_profile(request):
    if request.method == 'POST':
        form = UserProfileForm(
            request.POST,
            instance=request.user
        )

        if form.is_valid():
            changed_fields = list(form.changed_data)

            with transaction.atomic():
                account = form.save()

                if changed_fields:
                    changed_field_labels = [
                        str(
                            form.fields[field_name].label
                            or field_name.replace('_', ' ').title()
                        )
                        for field_name in changed_fields
                    ]

                    create_audit_log(
                        actor=account,
                        action='PROFILE_UPDATED',
                        reference=f'User #{account.pk}',
                        description=(
                            'Updated profile fields: '
                            f'{", ".join(changed_field_labels)}.'
                        )
                    )

            messages.success(
                request,
                'Profile updated successfully.'
            )

            return redirect('user_profile')

    else:
        form = UserProfileForm(
            instance=request.user
        )

    return render(
        request,
        'Reservation/user/UserProfile.html',
        {
            'form': form
        }
    )


# =========================================================
# BASIC USER U2 - FACILITIES
# =========================================================

@basic_user_required
def browse_facilities(request):
    search_query = request.GET.get(
        'search',
        ''
    ).strip()

    category_filter, category_id = parse_positive_id_filter(
        request.GET.get('category', '')
    )

    capacity_filter = request.GET.get(
        'capacity',
        ''
    ).strip()

    facilities = (
        Facility.objects
        .filter(
            is_active=True,
            category__is_active=True
        )
        .select_related('category')
    )

    if search_query:
        facilities = facilities.filter(
            Q(name__icontains=search_query)
            | Q(location__icontains=search_query)
            | Q(facility_code__icontains=search_query)
        )

    if category_id is not None:
        facilities = facilities.filter(
            category_id=category_id
        )

    if capacity_filter:
        try:
            capacity_value = int(
                capacity_filter
            )

            facilities = facilities.filter(
                capacity__gte=capacity_value
            )

        except ValueError:
            pass

    categories = FacilityCategory.objects.filter(
        is_active=True
    ).order_by('name')

    return render(
        request,
        'Reservation/user/FacilityBrowse.html',
        {
            'facilities': facilities,
            'categories': categories,
            'search_query': search_query,
            'category_filter': category_filter,
            'capacity_filter': capacity_filter,
        }
    )


@basic_user_required
def facility_detail_user(request, facility_id):
    facility = get_object_or_404(
        Facility.objects.select_related('category'),
        pk=facility_id,
        is_active=True,
        category__is_active=True
    )

    amenities = Amenity.objects.filter(
        is_active=True,
        facility_amenities__facility=facility
    ).order_by('name')

    now = timezone.now()
    today = timezone.localdate()
    booking_settings = get_system_settings()
    availability_days = booking_settings.advance_booking_days

    unavailable_slots = list(
        Reservation.objects
        .filter(
            facility=facility,
            status__in=[
                'APPROVED',
                'CHECKED_IN',
            ],
            end_datetime__gte=now
        )
        .values(
            'start_datetime',
            'end_datetime'
        )
        .order_by('start_datetime')
    )

    closure_slots = list(
        ClosureBlock.objects
        .filter(
            facility=facility,
            is_active=True,
            end_datetime__gte=now
        )
        .values(
            'start_datetime',
            'end_datetime'
        )
        .order_by('start_datetime')
    )

    available_slots = []

    for day_offset in range(availability_days):

        current_date = today + timedelta(days=day_offset)

        opening_datetime = timezone.make_aware(
            datetime.combine(
                current_date,
                facility.opening_time
            )
        )

        closing_datetime = timezone.make_aware(
            datetime.combine(
                current_date,
                facility.closing_time
            )
        )

        slot_start = max(
            opening_datetime,
            now
        )

        if slot_start >= closing_datetime:
            continue

        reservation_blocks = [
            block
            for block in unavailable_slots
            if (
                block['start_datetime'] < closing_datetime
                and block['end_datetime'] > opening_datetime
            )
        ]

        closure_blocks = [
            block
            for block in closure_slots
            if (
                block['start_datetime'] < closing_datetime
                and block['end_datetime'] > opening_datetime
            )
        ]

        blocked_periods = []

        for block in reservation_blocks:
            blocked_periods.append(
                (
                    max(
                        block['start_datetime'],
                        opening_datetime
                    ),
                    min(
                        block['end_datetime'],
                        closing_datetime
                    )
                )
            )

        for block in closure_blocks:
            blocked_periods.append(
                (
                    max(
                        block['start_datetime'],
                        opening_datetime
                    ),
                    min(
                        block['end_datetime'],
                        closing_datetime
                    )
                )
            )

        blocked_periods.sort(
            key=lambda period: period[0]
        )

        merged_blocks = []

        for block_start, block_end in blocked_periods:

            if not merged_blocks:
                merged_blocks.append(
                    [block_start, block_end]
                )
                continue

            previous_start, previous_end = (
                merged_blocks[-1]
            )

            if block_start <= previous_end:
                merged_blocks[-1][1] = max(
                    previous_end,
                    block_end
                )
            else:
                merged_blocks.append(
                    [block_start, block_end]
                )

        current_start = slot_start

        for block_start, block_end in merged_blocks:

            if block_end <= current_start:
                continue

            if block_start > current_start:
                available_slots.append({
                    'date': current_date,
                    'start_datetime': current_start,
                    'end_datetime': block_start,
                })

            current_start = max(
                current_start,
                block_end
            )

        if current_start < closing_datetime:
            available_slots.append({
                'date': current_date,
                'start_datetime': current_start,
                'end_datetime': closing_datetime,
            })

    # Offer an editable starting point, not a claim that a slot is held.
    for slot in available_slots:
        # A suggestion leaves time to complete the form; this is not a booking rule.
        start = max(timezone.localtime(slot['start_datetime']), timezone.localtime(now) + timedelta(minutes=10))
        rounded_start = start.replace(second=0, microsecond=0)
        if rounded_start < start:
            rounded_start += timedelta(minutes=1)
        end = min(
            timezone.localtime(slot['end_datetime']).replace(second=0, microsecond=0),
            rounded_start + timedelta(hours=min(1, booking_settings.max_event_duration_hours)),
        )
        if end > rounded_start:
            slot['booking_start'] = rounded_start
            slot['booking_url'] = reverse('reservation_create') + '?' + urlencode({
                'facility': facility.pk,
                'start_datetime': rounded_start.strftime('%Y-%m-%dT%H:%M'),
                'end_datetime': end.strftime('%Y-%m-%dT%H:%M'),
            })

    return render(
        request,
        'Reservation/user/FacilityDetail.html',
        {
            'facility': facility,
            'amenities': amenities,
            'available_slots': available_slots,
            'unavailable_slots': unavailable_slots,
            'closure_slots': closure_slots,
            'availability_days': availability_days,
        }
    )


# =========================================================
# BASIC USER U3 - REQUEST RESERVATION
# =========================================================

@basic_user_required
@workspace_editor('browse_facilities')
def reservation_create(request):
    if request.method == 'POST':
        form = ReservationRequestForm(
            request.POST
        )

        if form.is_valid():
            try:
                reservation = (
                    create_reservation_request(
                        user=request.user,
                        facility=form.cleaned_data[
                            'facility'
                        ],
                        event_name=form.cleaned_data[
                            'event_name'
                        ],
                        purpose=form.cleaned_data[
                            'purpose'
                        ],
                        expected_attendees=form.cleaned_data[
                            'expected_attendees'
                        ],
                        start_datetime=form.cleaned_data[
                            'start_datetime'
                        ],
                        end_datetime=form.cleaned_data[
                            'end_datetime'
                        ]
                    )
                )

                messages.success(
                    request,
                    'Reservation request submitted. '
                    'Status: Pending.'
                )

                return redirect(
                    'reservation_detail_user',
                    reservation_id=reservation.pk
                )

            except ValidationError as error:
                form.add_error(
                    None,
                    ' '.join(error.messages)
                )

    else:

        initial = {}

        facility_id = request.GET.get('facility')

        if facility_id:
            initial['facility'] = facility_id

        form = ReservationRequestForm(initial=initial)
        # GET values only prefill an unbound form. POST always uses its own data
        # and the existing service rechecks hours, capacity, conflicts and limits.
        try:
            start = datetime.strptime(request.GET.get('start_datetime', '')[:32], '%Y-%m-%dT%H:%M')
            end = datetime.strptime(request.GET.get('end_datetime', '')[:32], '%Y-%m-%dT%H:%M')
            if start < end:
                form.initial.update(start_datetime=start, end_datetime=end)
        except (ValueError, TypeError):
            pass

    return render(
        request,
        'Reservation/user/ReservationForm.html',
        {
            'form': form
        }
    )


# =========================================================
# BASIC USER U4 - OWN RESERVATIONS
# =========================================================

@basic_user_required
def my_reservations(request):
    now = timezone.now()
    records = Reservation.objects.filter(user=request.user).select_related('facility')
    has_reservations = records.exists()
    search = request.GET.get('search', '').strip()[:200]
    status = request.GET.get('status', '')
    period = request.GET.get('period', 'all')
    if status not in dict(Reservation.STATUS_CHOICES):
        status = ''
    if period not in ('all', 'upcoming', 'past'):
        period = 'all'
    if search:
        records = records.filter(Q(event_name__icontains=search) | Q(facility__name__icontains=search))
    if status:
        records = records.filter(status=status)
    if period == 'upcoming':
        records = records.filter(end_datetime__gt=now,
                                 status__in=['PENDING', 'APPROVED', 'CHECKED_IN'])
    elif period == 'past':
        records = records.filter(end_datetime__lte=now)
    ordering = ('start_datetime', 'pk') if period == 'upcoming' else ('-start_datetime', '-pk')
    page = Paginator(records.order_by(*ordering), 25).get_page(request.GET.get('page'))
    return render(request, 'Reservation/user/MyReservations.html', {
        'reservations': page.object_list, 'page_obj': page,
        'has_reservations': has_reservations, 'search_query': search,
        'status_filter': status, 'period_filter': period,
        'status_choices': Reservation.STATUS_CHOICES,
        'filters_active': bool(search or status or period != 'all'),
        'directory_query': urlencode({'search': search, 'status': status, 'period': period}),
        'schedule_now': now,
    })


@basic_user_required
def reservation_detail_user(
    request,
    reservation_id
):
    reservation = get_object_or_404(
        Reservation.objects.select_related(
            'facility'
        ),
        pk=reservation_id,
        user=request.user
    )

    return render(
        request,
        'Reservation/user/ReservationDetail.html',
        {
            'reservation': reservation,
            'schedule_now': timezone.now(),
        }
    )


@basic_user_required
def reservation_cancel_user(
    request,
    reservation_id
):
    reservation = get_object_or_404(
        Reservation,
        pk=reservation_id,
        user=request.user
    )

    if request.method != 'POST':
        return redirect(
            'reservation_detail_user',
            reservation_id=reservation.pk
        )

    try:
        cancel_reservation(
            reservation_id=reservation_id,
            user=request.user
        )

        messages.success(
            request,
            'Reservation cancelled successfully.'
        )

    except ValidationError as error:
        messages.error(
            request,
            ' '.join(error.messages)
        )

    return redirect(
        'reservation_detail_user',
        reservation_id=reservation.pk
    )
