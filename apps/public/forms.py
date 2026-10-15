import re

from django import forms
from .models import Inquiry


class InquiryForm(forms.ModelForm):
    class Meta:
        model = Inquiry
        fields = [
            'name',
            'email',
            'phone',
            'hotel',
            'comment',
        ]

    def clean_name(self):
        name = self.cleaned_data['name'].strip()

        if len(name) < 2:
            raise forms.ValidationError(
                'Please enter your name.'
            )

        return name

    def clean_phone(self):
        phone = self.cleaned_data['phone'].strip()

        # Extract digits for length validation.
        digits = re.sub(r'\D', '', phone)

        # Allow digits, spaces, +, hyphens, and parentheses.
        if not re.fullmatch(r'[\d\s+()-]+', phone):
            raise forms.ValidationError(
                'Enter a valid phone number.'
            )

        if not 7 <= len(digits) <= 15:
            raise forms.ValidationError(
                'Enter a valid phone number with 7 to 15 digits.'
            )

        return phone

    def clean_comment(self):
        comment = self.cleaned_data['comment'].strip()

        # Reject empty comments but allow short messages.
        if not comment:
            raise forms.ValidationError(
                'Please tell us how we can help.'
            )

        # Maximum comment length: 2000 characters.
        if len(comment) > 2000:
            raise forms.ValidationError(
                'Please keep your message under 2000 characters.'
            )

        return comment
