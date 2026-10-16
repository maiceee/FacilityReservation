import csv

from django.contrib import messages
from django.contrib.auth import logout
from django.core.exceptions import ValidationError
from django.db.models import Count, Q, Sum, F, ExpressionWrapper, DurationField
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from datetime import datetime, timedelta
from django.core.paginator import Paginator

from .decorators import admin_required, basic_user_required
from .forms import (
    UserRegistrationForm,
    UserProfileForm,
    FacilityCategoryForm,
    AmenityForm,
    FacilityForm,
    ReservationRequestForm,
    ReservationDecisionForm,
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
    reschedule_reservation,
    check_in_reservation,
    complete_reservation,
    mark_no_show,
    get_system_settings,
)


# =========================================================
# AUTHENTICATION
# =========================================================

def register(request):
    if request.user.is_authenticated:
        return redirect('dashboard_redirect')

    if request.method == 'POST':
        form = UserRegistrationForm(request.POST)

        if form.is_valid():
            form.save()

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

    pending_requests = Reservation.objects.filter(
        status='PENDING'
    ).count()

    approved_upcoming = Reservation.objects.filter(
        status='APPROVED',
        start_datetime__gte=now
    ).count()

    completed_events = Reservation.objects.filter(
        status='COMPLETED'
    ).count()

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

        booking_count = Reservation.objects.filter(
            start_datetime__date__gte=month_start,
            start_datetime__date__lt=next_month_start
        ).count()

        monthly_labels.append(
            month_start.strftime('%b %Y')
        )

        monthly_booking_data.append(
            booking_count
        )

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
        'last_name',
        'first_name',
        'username'
    )

    return render(
        request,
        'Reservation/admin/users/UserManagement.html',
        {
            'users': users,
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
    categories = FacilityCategory.objects.order_by(
        'name'
    )

    return render(
        request,
        'Reservation/admin/facilities/CategoryList.html',
        {
            'categories': categories
        }
    )


@admin_required
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
    amenities = Amenity.objects.order_by(
        'name'
    )

    return render(
        request,
        'Reservation/admin/facilities/AmenityList.html',
        {
            'amenities': amenities
        }
    )


@admin_required
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
    search_query = request.GET.get(
        'search',
        ''
    ).strip()

    facilities = (
        Facility.objects
        .select_related('category')
    )

    if search_query:
        facilities = facilities.filter(
            Q(facility_code__icontains=search_query)
            | Q(name__icontains=search_query)
            | Q(location__icontains=search_query)
            | Q(category__name__icontains=search_query)
        )

    facilities = facilities.order_by(
        'name'
    )

    return render(
        request,
        'Reservation/admin/facilities/FacilityList.html',
        {
            'facilities': facilities,
            'search_query': search_query,
        }
    )


@admin_required
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

    facility_filter = request.GET.get(
        'facility',
        ''
    ).strip()

    date_filter = request.GET.get(
        'date',
        ''
    ).strip()

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

    if facility_filter:
        try:
            reservations = reservations.filter(
                facility_id=int(facility_filter)
            )
        except (TypeError, ValueError):
            facility_filter = ''

    if date_filter:
        reservations = reservations.filter(
            start_datetime__date=date_filter
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
    facility_value = request.GET.get('facility', '').strip()

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

    if facility_value:
        try:
            reservations = reservations.filter(
                facility_id=int(facility_value)
            )
        except (TypeError, ValueError):
            facility_value = ''

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

    if facility_value:
        closures = closures.filter(
            facility_id=facility_value
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
        .order_by('-start_datetime')
    )

    return render(
        request,
        'Reservation/admin/closures/ClosureList.html',
        {
            'closures': closures
        }
    )


@admin_required
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

    closure = get_object_or_404(
        ClosureBlock,
        pk=closure_id
    )

    closure.is_active = False
    closure.archived_at = timezone.now()

    closure.save(
        update_fields=[
            'is_active',
            'archived_at',
        ]
    )

    create_audit_log(
        actor=request.user,
        action='CLOSURE_ARCHIVED',
        reference=f'Closure #{closure.pk}',
        description=closure.reason
    )

    messages.success(
        request,
        'Closure archived successfully.'
    )

    return redirect('closure_list')


# =========================================================
# ADMIN A7 - REPORTS
# =========================================================

@admin_required
def reports(request):
    start_date = request.GET.get(
        'start_date',
        ''
    ).strip()

    end_date = request.GET.get(
        'end_date',
        ''
    ).strip()

    reservations = (
        Reservation.objects
        .select_related(
            'facility',
            'user'
        )
        .order_by('-start_datetime')
    )

    if start_date:
        reservations = reservations.filter(
            start_datetime__date__gte=start_date
        )

    if end_date:
        reservations = reservations.filter(
            start_datetime__date__lte=end_date
        )

    total_reservations = reservations.count()

    completed_reservations = reservations.filter(
        status='COMPLETED'
    ).count()

    facilities = Facility.objects.order_by(
        'name'
    )

    facility_usage_rows = []
    total_booked_hours = 0

    for facility in facilities:

        facility_reservations = (
            Reservation.objects
            .filter(
                facility=facility,
                status__in=[
                    'APPROVED',
                    'CHECKED_IN',
                    'COMPLETED',
                    'NO_SHOW',
                ]
            )
        )

        if start_date:
            facility_reservations = (
                facility_reservations.filter(
                    start_datetime__date__gte=start_date
                )
            )

        if end_date:
            facility_reservations = (
                facility_reservations.filter(
                    start_datetime__date__lte=end_date
                )
            )

        completed_events = (
            facility_reservations
            .filter(
                status='COMPLETED'
            )
            .count()
        )

        booked_duration = (
            facility_reservations
            .annotate(
                reservation_duration=ExpressionWrapper(
                    F('end_datetime') - F('start_datetime'),
                    output_field=DurationField()
                )
            )
            .aggregate(
                total_duration=Sum(
                    'reservation_duration'
                )
            )['total_duration']
        )

        if booked_duration:
            booked_hours = (
                booked_duration.total_seconds()
                / 3600
            )
        else:
            booked_hours = 0

        total_booked_hours += booked_hours

        facility_usage_rows.append({
            'facility': facility,
            'completed_events': completed_events,
            'booked_hours': round(
                booked_hours,
                2
            ),
        })

    total_booked_hours = round(
        total_booked_hours,
        2
    )

    return render(
        request,
        'Reservation/admin/reports/Reports.html',
        {
            'reservations': reservations,
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
    start_date = request.GET.get(
        'start_date',
        ''
    )

    end_date = request.GET.get(
        'end_date',
        ''
    )

    reservations = (
        Reservation.objects
        .select_related(
            'facility',
            'user'
        )
        .order_by('start_datetime')
    )

    if start_date:
        reservations = reservations.filter(
            start_datetime__date__gte=start_date
        )

    if end_date:
        reservations = reservations.filter(
            start_datetime__date__lte=end_date
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
        '-timestamp'
    )

    return render(
        request,
        'Reservation/admin/reports/AuditLogs.html',
        {
            'logs': logs,
            'search_query': search_query,
        }
    )


# =========================================================
# ADMIN A8 - SYSTEM SETTINGS
# =========================================================

@admin_required
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
    upcoming = (
        Reservation.objects
        .filter(
            user=request.user,
            start_datetime__gte=timezone.now()
        )
        .exclude(
            status__in=[
                'REJECTED',
                'CANCELLED',
            ]
        )
        .select_related('facility')
        .order_by('start_datetime')[:5]
    )

    return render(
        request,
        'Reservation/user/UserDashboard.html',
        {
            'upcoming_reservations': upcoming
        }
    )


# =========================================================
# BASIC USER U1 - PROFILE
# =========================================================

@basic_user_required
def user_profile(request):
    if request.method == 'POST':
        form = UserProfileForm(
            request.POST,
            instance=request.user
        )

        if form.is_valid():
            form.save()

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

    category_filter = request.GET.get(
        'category',
        ''
    ).strip()

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

    if category_filter:
        facilities = facilities.filter(
            category_id=category_filter
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

    unavailable_slots = (
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

    closure_slots = (
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

    for day_offset in range(7):

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

        reservation_blocks = (
            Reservation.objects
            .filter(
                facility=facility,
                status__in=[
                    'APPROVED',
                    'CHECKED_IN',
                ],
                start_datetime__lt=closing_datetime,
                end_datetime__gt=opening_datetime
            )
            .values(
                'start_datetime',
                'end_datetime'
            )
        )

        closure_blocks = (
            ClosureBlock.objects
            .filter(
                facility=facility,
                is_active=True,
                start_datetime__lt=closing_datetime,
                end_datetime__gt=opening_datetime
            )
            .values(
                'start_datetime',
                'end_datetime'
            )
        )

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

    return render(
        request,
        'Reservation/user/FacilityDetail.html',
        {
            'facility': facility,
            'amenities': amenities,
            'available_slots': available_slots,
            'unavailable_slots': unavailable_slots,
            'closure_slots': closure_slots,
        }
    )


# =========================================================
# BASIC USER U3 - REQUEST RESERVATION
# =========================================================

@basic_user_required
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

        form = ReservationRequestForm(
            initial=initial
        )

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
    reservations = (
        Reservation.objects
        .filter(
            user=request.user
        )
        .select_related('facility')
        .order_by('-start_datetime')
    )

    return render(
        request,
        'Reservation/user/MyReservations.html',
        {
            'reservations': reservations
        }
    )


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
            'reservation': reservation
        }
    )


@basic_user_required
def reservation_cancel_user(
    request,
    reservation_id
):
    if request.method != 'POST':
        return redirect(
            'reservation_detail_user',
            reservation_id=reservation_id
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
        reservation_id=reservation_id
    )