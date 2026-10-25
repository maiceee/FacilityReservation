from django.urls import path
from django.contrib.auth import views as auth_views

from . import views
from .directory import directory_bulk
from .forms import AccountAuthenticationForm
from .notification_views import notification_feed, notification_read


urlpatterns = [
    path('notifications/', notification_feed, name='notification_feed'),
    path('notifications/read/', notification_read, name='notification_read'),
    path("manage/directory/<str:kind>/bulk/", directory_bulk, name="directory_bulk"),

    # =====================================================
    # AUTHENTICATION
    # =====================================================

    path(
        '',
        views.dashboard_redirect,
        name='dashboard_redirect'
    ),

    path(
        'register/',
        views.register,
        name='register'
    ),

    path(
        'login/',
        auth_views.LoginView.as_view(
            template_name='Reservation/registration/LoginForm.html',
            authentication_form=AccountAuthenticationForm,
            redirect_authenticated_user=True,
        ),
        name='login'
    ),

    path(
        'logout/',
        auth_views.LogoutView.as_view(
            next_page='login'
        ),
        name='logout'
    ),


    # =====================================================
    # ADMIN DASHBOARD
    # =====================================================

    path(
        'manage/',
        views.admin_dashboard,
        name='admin_dashboard'
    ),


    # =====================================================
    # ADMIN A1 - USER MANAGEMENT
    # =====================================================

    path(
        'manage/users/',
        views.user_management,
        name='user_management'
    ),

    path(
        'manage/users/<int:user_id>/',
        views.admin_user_detail,
        name='admin_user_detail'
    ),

    path(
        'manage/users/<int:user_id>/toggle-status/',
        views.toggle_user_status,
        name='toggle_user_status'
    ),


    # =====================================================
    # ADMIN A2 - FACILITY CATEGORIES
    # =====================================================

    path(
        'manage/categories/',
        views.category_list,
        name='category_list'
    ),

    path(
        'manage/categories/add/',
        views.category_create,
        name='category_create'
    ),

    path(
        'manage/categories/<int:category_id>/edit/',
        views.category_update,
        name='category_update'
    ),

    path(
        'manage/categories/<int:category_id>/archive/',
        views.category_archive,
        name='category_archive'
    ),


    # =====================================================
    # ADMIN A2 - AMENITIES
    # =====================================================

    path(
        'manage/amenities/',
        views.amenity_list,
        name='amenity_list'
    ),

    path(
        'manage/amenities/add/',
        views.amenity_create,
        name='amenity_create'
    ),

    path(
        'manage/amenities/<int:amenity_id>/edit/',
        views.amenity_update,
        name='amenity_update'
    ),

    path(
        'manage/amenities/<int:amenity_id>/archive/',
        views.amenity_archive,
        name='amenity_archive'
    ),


    # =====================================================
    # ADMIN A2 - FACILITIES
    # =====================================================

    path(
        'manage/facilities/',
        views.facility_list,
        name='facility_list'
    ),

    path(
        'manage/facilities/check-code/',
        views.facility_code_availability,
        name='facility_code_availability'
    ),

    path(
        'manage/facilities/add/',
        views.facility_create,
        name='facility_create'
    ),

    path(
        'manage/facilities/<int:facility_id>/edit/',
        views.facility_update,
        name='facility_update'
    ),

    path(
        'manage/facilities/<int:facility_id>/archive/',
        views.facility_archive,
        name='facility_archive'
    ),


    # =====================================================
    # ADMIN A3 - RESERVATION REVIEW
    # =====================================================

    path(
        'manage/reservations/',
        views.reservation_queue,
        name='reservation_queue'
    ),

    path(
        'manage/reservations/<int:reservation_id>/',
        views.reservation_detail_admin,
        name='reservation_detail_admin'
    ),

    path(
        'manage/reservations/<int:reservation_id>/approve/',
        views.reservation_approve,
        name='reservation_approve'
    ),

    path(
        'manage/reservations/<int:reservation_id>/reject/',
        views.reservation_reject,
        name='reservation_reject'
    ),

    path(
        'manage/reservations/<int:reservation_id>/cancel/',
        views.reservation_cancel_admin,
        name='reservation_cancel_admin'
    ),


    # =====================================================
    # ADMIN A4 - CALENDAR / RESCHEDULING
    # =====================================================

    path(
        'manage/calendar/',
        views.admin_calendar,
        name='admin_calendar'
    ),

    path(
        'manage/reservations/<int:reservation_id>/reschedule/',
        views.reservation_reschedule,
        name='reservation_reschedule'
    ),


    # =====================================================
    # ADMIN A5 - EVENT OPERATIONS
    # =====================================================

    path(
        'manage/reservations/<int:reservation_id>/check-in/',
        views.reservation_check_in,
        name='reservation_check_in'
    ),

    path(
        'manage/reservations/<int:reservation_id>/complete/',
        views.reservation_complete,
        name='reservation_complete'
    ),

    path(
        'manage/reservations/<int:reservation_id>/no-show/',
        views.reservation_no_show,
        name='reservation_no_show'
    ),

    path(
        'manage/reservations/<int:reservation_id>/slip/',
        views.reservation_slip,
        name='reservation_slip'
    ),

    path(
        'manage/reservations/<int:reservation_id>/completion-summary/',
        views.completion_summary,
        name='completion_summary'
    ),


    # =====================================================
    # ADMIN A6 - CLOSURES
    # =====================================================

    path(
        'manage/closures/',
        views.closure_list,
        name='closure_list'
    ),

    path(
        'manage/closures/add/',
        views.closure_create,
        name='closure_create'
    ),

    path(
        'manage/closures/<int:closure_id>/archive/',
        views.closure_archive,
        name='closure_archive'
    ),


    # =====================================================
    # ADMIN A7 - REPORTS
    # =====================================================

    path(
        'manage/reports/',
        views.reports,
        name='reports'
    ),

    path(
        'manage/reports/reservations/csv/',
        views.export_reservations_csv,
        name='export_reservations_csv'
    ),

    path(
        'manage/reports/facility-utilization/csv/',
        views.export_facility_usage_csv,
        name='export_facility_usage_csv'
    ),


    # =====================================================
    # ADMIN A8 - AUDIT LOGS / SETTINGS
    # =====================================================

    path(
        'manage/audit-logs/',
        views.audit_logs,
        name='audit_logs'
    ),

    path(
        'manage/settings/',
        views.system_settings,
        name='system_settings'
    ),


    # =====================================================
    # BASIC USER DASHBOARD
    # =====================================================

    path(
        'portal/',
        views.user_dashboard,
        name='user_dashboard'
    ),


    # =====================================================
    # BASIC USER U1 - PROFILE
    # =====================================================

    path(
        'portal/profile/',
        views.user_profile,
        name='user_profile'
    ),


    # =====================================================
    # BASIC USER U2 - FACILITIES
    # =====================================================

    path(
        'portal/facilities/',
        views.browse_facilities,
        name='browse_facilities'
    ),

    path(
        'portal/facilities/<int:facility_id>/',
        views.facility_detail_user,
        name='facility_detail_user'
    ),


    # =====================================================
    # BASIC USER U3 - RESERVATION REQUEST
    # =====================================================

    path(
        'portal/reservations/request/',
        views.reservation_create,
        name='reservation_create'
    ),


    # =====================================================
    # BASIC USER U4 - OWN RESERVATIONS
    # =====================================================

    path(
        'portal/reservations/',
        views.my_reservations,
        name='my_reservations'
    ),

    path(
        'portal/reservations/<int:reservation_id>/',
        views.reservation_detail_user,
        name='reservation_detail_user'
    ),

    path(
        'portal/reservations/<int:reservation_id>/cancel/',
        views.reservation_cancel_user,
        name='reservation_cancel_user'
    ),
]
