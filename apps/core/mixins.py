from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.exceptions import PermissionDenied


class ModulePermissionRequiredMixin(LoginRequiredMixin):
    """
    Set `module` and `permission_action` ('view'|'add'|'edit'|'delete')
    on the view class. Same enforcement logic as the function decorator,
    reused here for CreateView/UpdateView/ListView etc.
    """
    module = None
    permission_action = 'view'

    def dispatch(self, request, *args, **kwargs):
        if not request.user.is_authenticated:
            return super().dispatch(request, *args, **kwargs)  # LoginRequiredMixin handles redirect

        if not request.user.is_superuser:
            staff_profile = getattr(request.user, 'staff_profile', None)
            if not staff_profile or not staff_profile.is_active:
                raise PermissionDenied("No active staff profile for this account.")
            if not staff_profile.has_permission(self.module, self.permission_action):
                raise PermissionDenied(
                    f"You don't have '{self.permission_action}' access to {self.module}."
                )
        return super().dispatch(request, *args, **kwargs)