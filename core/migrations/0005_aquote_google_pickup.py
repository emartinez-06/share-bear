# Generated for Google Calendar pickup fields

import django.utils.timezone
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0004_aquote_admin_confirmed_offer"),
    ]

    operations = [
        migrations.AlterField(
            model_name="aiquote",
            name="booking_link",
            field=models.URLField(
                blank=True,
                help_text="Optional manual link (legacy) if Calendar pickup is not used.",
                max_length=1024,
            ),
        ),
        migrations.AddField(
            model_name="aiquote",
            name="google_calendar_id",
            field=models.CharField(
                blank=True,
                help_text="Google Calendar id for the pickup event (e.g. email@example.com).",
                max_length=256,
            ),
        ),
        migrations.AddField(
            model_name="aiquote",
            name="google_event_id",
            field=models.TextField(
                blank=True, help_text="Google Calendar event id for the chosen pickup slot."
            ),
        ),
        migrations.AddField(
            model_name="aiquote",
            name="pickup_ends_at",
            field=models.DateTimeField(
                blank=True, help_text="End of the pickup event (from Google).", null=True
            ),
        ),
        migrations.AddField(
            model_name="aiquote",
            name="pickup_event_html_link",
            field=models.URLField(
                blank=True,
                help_text="Link to open the pickup event in Google Calendar.",
                max_length=2000,
            ),
        ),
        migrations.AddField(
            model_name="aiquote",
            name="pickup_starts_at",
            field=models.DateTimeField(
                blank=True, help_text="Start of the pickup event (from Google).", null=True
            ),
        ),
    ]
