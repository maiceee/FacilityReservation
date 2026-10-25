from functools import wraps
from urllib.parse import urlencode

from django.contrib import messages
from django.contrib.auth import SESSION_KEY, logout
from django.shortcuts import redirect
from django.http import JsonResponse
from django.urls import reverse
from django.views.decorators.cache import never_cache


def workspace_editor(workspace, *, workspace_args=()):
    """Present protected forms in their workspace; keep normal form contracts.

    The editor header selects the HTML form for GET/errors and a save receipt
    for successful POST. Returning a receipt avoids fetching the destination
    twice and consuming its success message before the browser navigates there.
    Role decorators must remain outside this presentation decorator.
    """
    def decorate(view_function):
        @wraps(view_function)
        def wrapper(request, *args, **kwargs):
            editing = request.headers.get('X-Spasyo-Editor') == '1'
            if request.method == 'GET' and not editing:
                home = reverse(
                    workspace,
                    kwargs={name: kwargs[name] for name in workspace_args},
                )
                return redirect(f'{home}?{urlencode({"editor": request.get_full_path()})}')

            response = view_function(request, *args, **kwargs)
            if editing and request.method == 'POST' and response.status_code == 302:
                return JsonResponse({'saved': True, 'redirect_url': response.url})
            return response
        return wrapper
    return decorate


def admin_required(view_function):
    @wraps(view_function)
    @never_cache
    def wrapper(request, *args, **kwargs):

        if not request.user.is_authenticated:
            if SESSION_KEY in request.session:
                logout(request)
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
    @never_cache
    def wrapper(request, *args, **kwargs):

        if not request.user.is_authenticated:
            if SESSION_KEY in request.session:
                logout(request)
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
