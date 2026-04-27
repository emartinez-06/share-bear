from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0005_aquote_google_pickup'),
    ]

    operations = [
        migrations.AddField(
            model_name='aiquote',
            name='booking_initiated',
            field=models.BooleanField(
                default=False,
                help_text='True once the user has been redirected to Google Booking for this item.',
            ),
        ),
    ]
