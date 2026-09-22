from django.contrib import messages
from django.views.generic import ListView, CreateView, UpdateView, DeleteView

from apps.core.mixins import ModulePermissionRequiredMixin

class BaseListView(ModulePermissionRequiredMixin, ListView):
    permission_action = 'view'
    paginate_by = 20
    template_name = 'dashboard/shared/list.html'

    page_title = 'Records'
    singular_name = 'Record'
    columns = []
    add_url_name = None
    edit_url_name = None
    delete_url_name = None
    view_url_name = None  # NEW: optional read-only "View" link (e.g. printable invoice)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        staff_profile = getattr(self.request.user, 'staff_profile', None)
        if self.request.user.is_superuser:
            context['can_add'] = context['can_edit'] = context['can_delete'] = True
        else:
            context['can_add'] = staff_profile.has_permission(self.module, 'add')
            context['can_edit'] = staff_profile.has_permission(self.module, 'edit')
            context['can_delete'] = staff_profile.has_permission(self.module, 'delete')

        context['page_title'] = self.page_title
        context['singular_name'] = self.singular_name
        context['columns'] = self.columns
        context['add_url_name'] = self.add_url_name
        context['edit_url_name'] = self.edit_url_name
        context['delete_url_name'] = self.delete_url_name
        context['view_url_name'] = self.view_url_name
        return context
        
class BaseCreateView(ModulePermissionRequiredMixin, CreateView):
    permission_action = 'add'
    template_name = 'dashboard/shared/form.html'
    page_title = 'Add Record'
    success_message = 'Record created successfully.'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = self.page_title
        # Use the static success_url directly — self.object doesn't exist yet on GET,
        # so calling get_success_url() here would crash (it needs self.object.__dict__).
        context['cancel_url'] = str(self.success_url)
        return context

    def form_valid(self, form):
        response = super().form_valid(form)
        messages.success(self.request, self.success_message)
        return response


class BaseUpdateView(ModulePermissionRequiredMixin, UpdateView):
    permission_action = 'edit'
    template_name = 'dashboard/shared/form.html'
    page_title = 'Edit Record'
    success_message = 'Record updated successfully.'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['page_title'] = self.page_title
        context['cancel_url'] = str(self.success_url)
        return context

    def form_valid(self, form):
        response = super().form_valid(form)
        messages.success(self.request, self.success_message)
        return response


class BaseDeleteView(ModulePermissionRequiredMixin, DeleteView):
    permission_action = 'delete'
    template_name = 'dashboard/shared/confirm_delete.html'
    success_message = 'Record deleted successfully.'

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['cancel_url'] = str(self.success_url)
        return context

    def delete(self, request, *args, **kwargs):
        response = super().delete(request, *args, **kwargs)
        messages.success(request, self.success_message)
        return response