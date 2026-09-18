from django import forms
from .models import Booking

TAILWIND_INPUT = (
    "w-full bg-ink-50 border border-ink-200 rounded-lg text-[13px] font-medium "
    "px-3.5 py-2.5 text-ink-900 placeholder-ink-400 focus:outline-none "
    "focus:border-brand-500 focus:bg-white focus:ring-4 focus:ring-brand-500/10 transition"
)
TAILWIND_CHECKBOX = "w-4 h-4 rounded border-ink-200 text-brand-500 focus:ring-brand-500 accent-brand-500"


class StyledModelForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name, field in self.fields.items():
            if isinstance(field.widget, forms.CheckboxInput):
                field.widget.attrs.setdefault('class', TAILWIND_CHECKBOX)
            else:
                field.widget.attrs.setdefault('class', TAILWIND_INPUT)


class BookingForm(StyledModelForm):
    class Meta:
        model = Booking
        fields = [
            'property', 'guest', 'check_in_date', 'check_out_date',
            'status', 'source', 'adults', 'children', 'special_requests',
            'paid_amount', 'is_active',
        ]
        widgets = {
            'check_in_date': forms.DateInput(attrs={'type': 'date'}),
            'check_out_date': forms.DateInput(attrs={'type': 'date'}),
        }