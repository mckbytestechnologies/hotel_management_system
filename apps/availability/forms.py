from django import forms
from .models import RoomRate

TAILWIND_INPUT = (
    "w-full bg-ink-50 border border-ink-200 rounded-lg text-[13px] font-medium "
    "px-3.5 py-2.5 text-ink-900 placeholder-ink-400 focus:outline-none "
    "focus:border-brand-500 focus:bg-white focus:ring-4 focus:ring-brand-500/10 transition"
)


class StyledModelForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name, field in self.fields.items():
            field.widget.attrs.setdefault('class', TAILWIND_INPUT)


class RoomRateForm(StyledModelForm):
    class Meta:
        model = RoomRate
        fields = ['property', 'room_type', 'rate_plan', 'date', 'base_price', 'extra_adult_price', 'extra_child_price', 'is_active']
        widgets = {'date': forms.DateInput(attrs={'type': 'date'})}


class BulkRateForm(forms.Form):
    property = forms.ModelChoiceField(queryset=None)
    room_type = forms.ModelChoiceField(queryset=None)
    rate_plan = forms.ModelChoiceField(queryset=None)
    start_date = forms.DateField(widget=forms.DateInput(attrs={'type': 'date'}))
    end_date = forms.DateField(widget=forms.DateInput(attrs={'type': 'date'}))
    base_price = forms.DecimalField(max_digits=10, decimal_places=2)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        from apps.properties.models import Property, RoomType, RatePlan
        self.fields['property'].queryset = Property.objects.filter(is_active=True)
        self.fields['room_type'].queryset = RoomType.objects.filter(is_active=True)
        self.fields['rate_plan'].queryset = RatePlan.objects.filter(is_active=True)
        for name, field in self.fields.items():
            field.widget.attrs.setdefault('class', TAILWIND_INPUT)

    def clean(self):
        cleaned = super().clean()
        start, end = cleaned.get('start_date'), cleaned.get('end_date')
        if start and end and end < start:
            raise forms.ValidationError("End date cannot be before start date.")
        return cleaned