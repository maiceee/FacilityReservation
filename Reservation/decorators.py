from functools import wraps

from django.contrib import messages
from django.contrib.auth import logout
from django.shortcuts import redirect


def admin_required(view_function):
    @wraps(view_function)
    def wrapper(request, *args, **kwargs):

        if not request.user.is_authenticated:
            return redirect('login')

        if not request.user.is_active:
            logout(request)
            messages.error(
                request,
                'Your account is inactive.'
            )
            return redirect('login')

        if request.user.role != 'ADMIN':
            return redirect('user_dashboard')

        return view_function(
            request,
            *args,
            **kwargs
        )

    return wrapper


def basic_user_required(view_function):
    @wraps(view_function)
    def wrapper(request, *args, **kwargs):

        if not request.user.is_authenticated:
            return redirect('login')

        if not request.user.is_active:
            logout(request)
            messages.error(
                request,
                'Your account has been deactivated. '
                'Please contact an administrator.'
            )
            return redirect('login')

        if request.user.role != 'BASIC_USER':
            return redirect('admin_dashboard')

        return view_function(
            request,
            *args,
            **kwargs
        )

    return wrapper