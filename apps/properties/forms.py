from django import forms
from .models import Property, RoomType, Room, RatePlan


TAILWIND_INPUT = (
    "w-full bg-ink-50 border border-ink-200 rounded-lg text-[13px] font-medium "
    "px-3.5 py-2.5 text-ink-900 placeholder-ink-400 focus:outline-none "
    "focus:border-brand-500 focus:bg-white focus:ring-4 focus:ring-brand-500/10 transition"
)
TAILWIND_CHECKBOX = "w-4 h-4 rounded border-ink-200 text-brand-500 focus:ring-brand-500 accent-brand-500"


class StyledModelForm(forms.ModelForm):
    """
    Base form that auto-applies our Tailwind input classes to every field,
    so we never hand-style fields one by one per form.
    """
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name, field in self.fields.items():
            if isinstance(field.widget, forms.CheckboxInput):
                field.widget.attrs.setdefault('class', TAILWIND_CHECKBOX)
            else:
                field.widget.attrs.setdefault('class', TAILWIND_INPUT)


class PropertyForm(StyledModelForm):
    class Meta:
        model = Property
        fields = [
            'name', 'code', 'address', 'city', 'state', 'country',
            'phone', 'email', 'check_in_time', 'check_out_time',
            'tax_number', 'is_active',
        ]
        widgets = {
            'check_in_time': forms.TimeInput(attrs={'type': 'time'}),
            'check_out_time': forms.TimeInput(attrs={'type': 'time'}),
        }


class RoomTypeForm(StyledModelForm):
    class Meta:
        model = RoomType
        fields = [
            'property', 'name', 'code', 'description',
            'max_adults', 'max_children', 'max_occupancy', 'base_occupancy', 'is_active',
        ]


class RoomForm(StyledModelForm):
    class Meta:
        model = Room
        fields = ['property', 'room_type', 'room_number', 'floor', 'status', 'is_active']


class RatePlanForm(StyledModelForm):
    class Meta:
        model = RatePlan
        fields = [
            'property', 'name', 'code', 'description',
            'meal_plan', 'cancellation_policy', 'is_refundable', 'is_active',
        ]