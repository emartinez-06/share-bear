from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0008_add_performance_indexes'),
    ]

    operations = [
        migrations.AddField(
            model_name='aiquote',
            name='denied',
            field=models.BooleanField(
                default=False,
                db_index=True,
                help_text='Set when an admin has denied this buy-back submission.',
            ),
        ),
        migrations.AddField(
            model_name='aiquote',
            name='denial_reason',
            field=models.TextField(
                blank=True,
                help_text='Admin explanation shown to the user when their item is denied.',
            ),
        ),
    ]
