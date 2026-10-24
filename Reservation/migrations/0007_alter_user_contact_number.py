# Generated manually to keep the database field aligned with registration validation.

import django.core.validators
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('Reservation', '0006_rename_created_at_auditlog_timestamp_and_more'),
    ]

    operations = [
        migrations.AlterField(
            model_name='user',
            name='contact_number',
            field=models.CharField(
                blank=True,
                max_length=11,
                validators=[
                    django.core.validators.RegexValidator(
                        code='invalid_philippine_mobile_number',
                        message=(
                            'Enter an 11-digit Philippine mobile number '
                            'starting with 09 (for example, 09171234567).'
                        ),
                        regex='^09\\d{9}$',
                    )
                ],
            ),
        ),
    ]
