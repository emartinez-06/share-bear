# Generated manually for admin_confirmed_offer_display

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0003_kanban_fields"),
    ]

    operations = [
        migrations.AddField(
            model_name="aiquote",
            name="admin_confirmed_offer_display",
            field=models.CharField(
                blank=True,
                help_text="When set, overrides the AI-parsed offer for user-facing display (e.g. after admin review).",
                max_length=32,
            ),
        ),
    ]
