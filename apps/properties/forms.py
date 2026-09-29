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

class MultipleFileInput(forms.ClearableFileInput):
    allow_multiple_selected = True


class MultipleFileField(forms.FileField):
    """A file field that accepts several files in one upload."""
    def __init__(self, *args, **kwargs):
        kwargs.setdefault('widget', MultipleFileInput(attrs={'accept': 'image/*'}))
        super().__init__(*args, **kwargs)

    def clean(self, data, initial=None):
        single_clean = super().clean
        if isinstance(data, (list, tuple)):
            return [single_clean(d, initial) for d in data]
        return [single_clean(data, initial)] if data else []

MAX_IMAGE_MB = 5


class PropertyForm(StyledModelForm):
    new_images = MultipleFileField(
        required=False, label='Add images',
        help_text=f'You can select several. JPG/PNG/WebP, up to {MAX_IMAGE_MB} MB each.',
    )

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

    def clean_new_images(self):
        files = [f for f in self.cleaned_data.get('new_images', []) if f]
        for f in files:
            if not (f.content_type or '').startswith('image/'):
                raise forms.ValidationError(f'"{f.name}" is not an image.')
            if f.size > MAX_IMAGE_MB * 1024 * 1024:
                raise forms.ValidationError(f'"{f.name}" is larger than {MAX_IMAGE_MB} MB.')
        return files


class RoomTypeForm(StyledModelForm):
    class Meta:
        model = RoomType
        fields = [
            'property', 'name', 'code', 'description',
            'max_adults', 'max_children', 'max_occupancy', 'base_occupancy',
            'default_price', 'is_active',
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