from django import forms
from django.contrib.auth.forms import UserCreationForm

from .models import (
    User,
    FacilityCategory,
    Amenity,
    Facility,
    FacilityAmenity,
    Reservation,
    ClosureBlock,
    SystemSetting,
)


# =========================================================
# USER REGISTRATION
# =========================================================

class UserRegistrationForm(UserCreationForm):
    first_name = forms.CharField(
        max_length=150,
        required=True
    )

    last_name = forms.CharField(
        max_length=150,
        required=True
    )

    email = forms.EmailField(
        required=True
    )

    department = forms.CharField(
        max_length=100,
        required=True
    )

    contact_number = forms.CharField(
        max_length=20,
        required=True
    )

    class Meta:
        model = User
        fields = [
            'username',
            'first_name',
            'last_name',
            'email',
            'department',
            'contact_number',
            'password1',
            'password2',
        ]

    def clean_email(self):
        email = self.cleaned_data['email'].strip().lower()

        if User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError(
                'An account with this email already exists.'
            )

        return email

    def save(self, commit=True):
        user = super().save(commit=False)

        # Registration must always create BASIC USER only.
        user.role = 'BASIC_USER'

        if commit:
            user.save()

        return user


# =========================================================
# BASIC USER PROFILE
# =========================================================

class UserProfileForm(forms.ModelForm):

    class Meta:
        model = User
        fields = [
            'first_name',
            'last_name',
            'contact_number',
        ]

    def clean_email(self):
        email = self.cleaned_data['email'].strip().lower()

        duplicate = User.objects.filter(
            email__iexact=email
        ).exclude(
            pk=self.instance.pk
        ).exists()

        if duplicate:
            raise forms.ValidationError(
                'An account with this email already exists.'
            )

        return email


# =========================================================
# FACILITY CATEGORY
# =========================================================

class FacilityCategoryForm(forms.ModelForm):

    class Meta:
        model = FacilityCategory
        fields = [
            'name',
            'is_active',
        ]

    def clean_name(self):
        name = self.cleaned_data['name'].strip()

        duplicate = FacilityCategory.objects.filter(
            name__iexact=name
        ).exclude(
            pk=self.instance.pk
        ).exists()

        if duplicate:
            raise forms.ValidationError(
                'A facility category with this name already exists.'
            )

        return name


# =========================================================
# AMENITY
# =========================================================

class AmenityForm(forms.ModelForm):

    class Meta:
        model = Amenity
        fields = [
            'name',
            'is_active',
        ]

    def clean_name(self):
        name = self.cleaned_data['name'].strip()

        duplicate = Amenity.objects.filter(
            name__iexact=name
        ).exclude(
            pk=self.instance.pk
        ).exists()

        if duplicate:
            raise forms.ValidationError(
                'An amenity with this name already exists.'
            )

        return name


# =========================================================
# FACILITY
# =========================================================

class FacilityForm(forms.ModelForm):

    amenities = forms.ModelMultipleChoiceField(
        queryset=Amenity.objects.filter(is_active=True),
        required=False,
        widget=forms.CheckboxSelectMultiple
    )

    class Meta:
        model = Facility
        fields = [
            'facility_code',
            'name',
            'category',
            'location',
            'capacity',
            'description',
            'opening_time',
            'closing_time',
            'is_active',
            'amenities',
        ]

        widgets = {
            'description': forms.Textarea(
                attrs={'rows': 4}
            ),

            'opening_time': forms.TimeInput(
                attrs={'type': 'time'}
            ),

            'closing_time': forms.TimeInput(
                attrs={'type': 'time'}
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.fields['category'].queryset = (
            FacilityCategory.objects.filter(
                is_active=True
            )
        )

        if self.instance and self.instance.pk:
            self.fields['amenities'].initial = Amenity.objects.filter(
                facility_amenities__facility=self.instance
            )

    def clean_facility_code(self):
        facility_code = (
            self.cleaned_data['facility_code']
            .strip()
            .upper()
        )

        duplicate = Facility.objects.filter(
            facility_code__iexact=facility_code
        ).exclude(
            pk=self.instance.pk
        ).exists()

        if duplicate:
            raise forms.ValidationError(
                'This facility code is already in use.'
            )

        return facility_code

    def clean_capacity(self):
        capacity = self.cleaned_data['capacity']

        if capacity < 1:
            raise forms.ValidationError(
                'Facility capacity must be at least 1.'
            )

        return capacity

    def clean(self):
        cleaned_data = super().clean()

        opening_time = cleaned_data.get('opening_time')
        closing_time = cleaned_data.get('closing_time')

        if (
            opening_time and
            closing_time and
            opening_time >= closing_time
        ):
            self.add_error(
                'closing_time',
                'Closing time must be later than opening time.'
            )

        return cleaned_data

    def save(self, commit=True):
        facility = super().save(commit=commit)

        if commit:
            FacilityAmenity.objects.filter(
                facility=facility
            ).delete()

            amenities = self.cleaned_data.get('amenities')

            if amenities:
                FacilityAmenity.objects.bulk_create(
                    [
                        FacilityAmenity(
                            facility=facility,
                            amenity=amenity
                        )
                        for amenity in amenities
                    ]
                )

        return facility


# =========================================================
# BASIC USER RESERVATION REQUEST
# =========================================================

class ReservationRequestForm(forms.ModelForm):

    class Meta:
        model = Reservation

        fields = [
            'facility',
            'event_name',
            'purpose',
            'expected_attendees',
            'start_datetime',
            'end_datetime',
        ]

        widgets = {
            'purpose': forms.Textarea(
                attrs={'rows': 4}
            ),

            'start_datetime': forms.DateTimeInput(
                attrs={
                    'type': 'datetime-local'
                },
                format='%Y-%m-%dT%H:%M'
            ),

            'end_datetime': forms.DateTimeInput(
                attrs={
                    'type': 'datetime-local'
                },
                format='%Y-%m-%dT%H:%M'
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.fields['facility'].queryset = (
            Facility.objects.filter(
                is_active=True,
                category__is_active=True
            ).select_related('category')
        )

        self.fields[
            'start_datetime'
        ].input_formats = [
            '%Y-%m-%dT%H:%M'
        ]

        self.fields[
            'end_datetime'
        ].input_formats = [
            '%Y-%m-%dT%H:%M'
        ]


# =========================================================
# ADMIN RESERVATION DECISION
# =========================================================

class ReservationDecisionForm(forms.Form):

    decision_reason = forms.CharField(
        required=False,
        widget=forms.Textarea(
            attrs={'rows': 4}
        ),
        label='Reason'
    )


# =========================================================
# ADMIN RESERVATION RESCHEDULE
# =========================================================

class ReservationRescheduleForm(forms.Form):

    start_datetime = forms.DateTimeField(
        widget=forms.DateTimeInput(
            attrs={'type': 'datetime-local'},
            format='%Y-%m-%dT%H:%M'
        ),
        input_formats=[
            '%Y-%m-%dT%H:%M'
        ]
    )

    end_datetime = forms.DateTimeField(
        widget=forms.DateTimeInput(
            attrs={'type': 'datetime-local'},
            format='%Y-%m-%dT%H:%M'
        ),
        input_formats=[
            '%Y-%m-%dT%H:%M'
        ]
    )

    reason = forms.CharField(
        required=True,
        widget=forms.Textarea(
            attrs={'rows': 4}
        )
    )


# =========================================================
# FACILITY CLOSURE
# =========================================================

class ClosureBlockForm(forms.ModelForm):

    class Meta:
        model = ClosureBlock

        fields = [
            'facility',
            'start_datetime',
            'end_datetime',
            'reason',
        ]

        widgets = {
            'start_datetime': forms.DateTimeInput(
                attrs={'type': 'datetime-local'},
                format='%Y-%m-%dT%H:%M'
            ),

            'end_datetime': forms.DateTimeInput(
                attrs={'type': 'datetime-local'},
                format='%Y-%m-%dT%H:%M'
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.fields['facility'].queryset = (
            Facility.objects.filter(
                is_active=True
            )
        )

        self.fields[
            'start_datetime'
        ].input_formats = [
            '%Y-%m-%dT%H:%M'
        ]

        self.fields[
            'end_datetime'
        ].input_formats = [
            '%Y-%m-%dT%H:%M'
        ]

    def clean(self):
        cleaned_data = super().clean()

        start_datetime = cleaned_data.get(
            'start_datetime'
        )

        end_datetime = cleaned_data.get(
            'end_datetime'
        )

        if (
            start_datetime and
            end_datetime and
            end_datetime <= start_datetime
        ):
            self.add_error(
                'end_datetime',
                'End date and time must be later than start date and time.'
            )

        return cleaned_data


# =========================================================
# INCIDENT NOTES
# =========================================================

class IncidentNotesForm(forms.Form):

    incident_notes = forms.CharField(
        required=False,
        widget=forms.Textarea(
            attrs={'rows': 5}
        ),
        label='Incident Notes'
    )


# =========================================================
# SYSTEM SETTINGS
# =========================================================

class SystemSettingForm(forms.ModelForm):

    class Meta:
        model = SystemSetting

        fields = [
            'max_event_duration_hours',
            'advance_booking_days',
        ]

    def clean_max_event_duration_hours(self):
        value = self.cleaned_data[
            'max_event_duration_hours'
        ]

        if value < 1:
            raise forms.ValidationError(
                'Maximum event duration must be at least 1 hour.'
            )

        return value

    def clean_advance_booking_days(self):
        value = self.cleaned_data[
            'advance_booking_days'
        ]

        if value < 1:
            raise forms.ValidationError(
                'Advance booking window must be at least 1 day.'
            )

        return value