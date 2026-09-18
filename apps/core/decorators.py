from functools import wraps
from django.core.exceptions import PermissionDenied
from django.contrib.auth.decorators import login_required


def module_permission_required(module, action='view'):
    """
    Usage:
        @module_permission_required(Module.PROPERTIES, 'view')
        def property_list_view(request):
            ...

    Superusers always pass. Staff without an explicit StaffPermission
    row (or with the relevant can_<action> flag off) get a 403.
    """
    def decorator(view_func):
        @wraps(view_func)
        @login_required
        def _wrapped(request, *args, **kwargs):
            if request.user.is_superuser:
                return view_func(request, *args, **kwargs)

            staff_profile = getattr(request.user, 'staff_profile', None)
            if not staff_profile or not staff_profile.is_active:
                raise PermissionDenied("No active staff profile for this account.")

            if not staff_profile.has_permission(module, action):
                raise PermissionDenied(
                    f"You don't have '{action}' access to {module}."
                )

            return view_func(request, *args, **kwargs)
        return _wrapped
    return decorator