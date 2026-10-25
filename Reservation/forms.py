from datetime import timedelta

from django import forms
from django.contrib.auth.forms import AuthenticationForm, UserCreationForm
from django.utils import timezone

from .models import (
    User,
    philippine_mobile_validator,
    FacilityCategory,
    Amenity,
    Facility,
    FacilityAmenity,
    Reservation,
    ClosureBlock,
    SystemSetting,
)


def reservation_datetime_bounds():
    local_now = timezone.localtime()
    booking_settings = SystemSetting.objects.first()
    advance_booking_days = (
        booking_settings.advance_booking_days
        if booking_settings is not None
        else SystemSetting._meta.get_field(
            'advance_booking_days'
        ).get_default()
    )
    latest_booking_date = (
        local_now.date() + timedelta(days=advance_booking_days)
    )

    return (
        local_now.replace(
            second=0,
            microsecond=0,
        ).strftime('%Y-%m-%dT%H:%M'),
        f'{latest_booking_date.isoformat()}T23:59',
    )


# =========================================================
# AUTHENTICATION
# =========================================================

class AccountAuthenticationForm(AuthenticationForm):
    deactivated_message = (
        'Your account has been deactivated. You are currently unable to '
        'log in. Please contact the system administrator for assistance '
        'or to request account reactivation.'
    )

    def clean(self):
        try:
            return super().clean()
        except forms.ValidationError:
            username = self.cleaned_data.get('username')
            password = self.cleaned_data.get('password')

            if username and password:
                try:
                    account = User._default_manager.get_by_natural_key(
                        username
                    )
                except User.DoesNotExist:
                    account = None

                if (
                    account is not None
                    and not account.is_active
                    and account.check_password(password)
                ):
                    raise forms.ValidationError(
                        self.deactivated_message,
                        code='inactive',
                    )

            raise

    def confirm_login_allowed(self, user):
        if not user.is_active:
            raise forms.ValidationError(
                self.deactivated_message,
                code='inactive',
            )

        super().confirm_login_allowed(user)


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
        max_length=11,
        min_length=11,
        required=True,
        validators=[philippine_mobile_validator],
        help_text='Use 11 digits starting with 09, such as 09171234567.',
        widget=forms.TextInput(
            attrs={
                'inputmode': 'numeric',
                'autocomplete': 'tel-national',
                'pattern': r'09[0-9]{9}',
                'minlength': '11',
                'maxlength': '11',
                'placeholder': '09171234567',
            }
        )
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
        widgets = {
            'contact_number': forms.TextInput(
                attrs={
                    'inputmode': 'numeric',
                    'autocomplete': 'tel-national',
                    'pattern': r'09[0-9]{9}',
                    'minlength': '11',
                    'maxlength': '11',
                    'placeholder': '09171234567',
                }
            ),
        }

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
                'A facility with this code already exists. '
                'Enter a unique facility code.'
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

        minimum_datetime, maximum_datetime = (
            reservation_datetime_bounds()
        )

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

        self.fields['start_datetime'].widget.attrs['min'] = (
            minimum_datetime
        )
        self.fields['end_datetime'].widget.attrs['min'] = (
            minimum_datetime
        )
        self.fields['start_datetime'].widget.attrs['max'] = (
            maximum_datetime
        )
        self.fields['end_datetime'].widget.attrs['max'] = (
            maximum_datetime
        )

    def clean_start_datetime(self):
        start = self.cleaned_data['start_datetime']
        if start <= timezone.now():
            raise forms.ValidationError(
                'This start time has passed. Choose a future start time.'
            )
        return start


# =========================================================
# ADMIN RESERVATION DECISION
# =========================================================

class ReservationDecisionForm(forms.Form):

    decision_reason = forms.CharField(
        required=True,
        widget=forms.Textarea(
            attrs={'rows': 4}
        ),
        label='Reason',
        error_messages={
            'required': 'A decision reason is required.'
        }
    )


# =========================================================
# ADMIN RESERVATION CANCELLATION
# =========================================================

class ReservationCancellationForm(forms.Form):

    reason = forms.CharField(
        required=True,
        widget=forms.Textarea(
            attrs={'rows': 4}
        ),
        label='Cancellation reason'
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

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        minimum_datetime, maximum_datetime = (
            reservation_datetime_bounds()
        )

        for field_name in ('start_datetime', 'end_datetime'):
            self.fields[field_name].widget.attrs.update(
                {
                    'min': minimum_datetime,
                    'max': maximum_datetime,
                }
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

        labels = {
            'facility': 'Facility',
            'start_datetime': 'Closure starts',
            'end_datetime': 'Closure ends',
            'reason': 'Reason for closure',
        }

        help_texts = {
            'facility': 'Only active facilities can be selected.',
            'end_datetime': 'The facility becomes available after this time.',
            'reason': 'Briefly explain why the facility will be unavailable.',
        }

        widgets = {
            'start_datetime': forms.DateTimeInput(
                attrs={'type': 'datetime-local'},
                format='%Y-%m-%dT%H:%M'
            ),

            'end_datetime': forms.DateTimeInput(
                attrs={'type': 'datetime-local'},
                format='%Y-%m-%dT%H:%M'
            ),

            'reason': forms.Textarea(
                attrs={
                    'rows': 4,
                    'placeholder': (
                        'Example: Preventive maintenance or campus holiday'
                    ),
                }
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
