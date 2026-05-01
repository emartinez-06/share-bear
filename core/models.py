from django.conf import settings
from django.db import models

from .gemini_quote import format_share_bear_offer_display


class AIQuote(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='ai_quotes',
    )
    item_name = models.CharField(max_length=200)
    description = models.TextField()
    make = models.CharField(max_length=120, blank=True)
    model = models.CharField(max_length=120, blank=True)
    unknown_make_model = models.BooleanField(default=False)
    quote_text = models.TextField()
    has_video = models.BooleanField(
        default=False,
        db_index=True,
        help_text='True when the user uploaded an acceptance/condition video.',
    )
    video_path = models.CharField(
        max_length=1024,
        blank=True,
        help_text='Object path in Supabase Storage (quote-videos bucket).',
    )
    quote_accepted_by_admin = models.BooleanField(
        default=False,
        db_index=True,
        help_text='Set when an admin has reviewed the video and accepted the buy-back offer.',
    )
    quote_reviewed_at = models.DateTimeField(null=True, blank=True)
    booking_link = models.URLField(
        max_length=1024,
        blank=True,
        help_text='Optional manual link (legacy) if Calendar pickup is not used.',
    )
    booking_initiated = models.BooleanField(
        default=False,
        help_text='True once the user has been redirected to Google Booking for this item.',
    )
    google_calendar_id = models.CharField(
        max_length=256,
        blank=True,
        help_text='Google Calendar id for the pickup event (e.g. email@example.com).',
    )
    google_event_id = models.TextField(
        blank=True,
        help_text='Google Calendar event id for the chosen pickup slot.',
    )
    pickup_event_html_link = models.URLField(
        max_length=2000,
        blank=True,
        help_text='Link to open the pickup event in Google Calendar.',
    )
    pickup_starts_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text='Start of the pickup event (from Google).',
    )
    pickup_ends_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text='End of the pickup event (from Google).',
    )
    picked_up = models.BooleanField(
        default=False,
        db_index=True,
        help_text='Set when an admin marks the item as physically picked up.',
    )
    picked_up_at = models.DateTimeField(null=True, blank=True)
    assigned_admin_name = models.CharField(
        max_length=120,
        blank=True,
        help_text='Admin team member currently handling this item.',
    )
    pickup_label_color = models.CharField(
        max_length=32,
        blank=True,
        help_text='Physical tag color used after pickup (org inventory convention).',
    )
    pickup_label_number = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text='Physical tag number used after pickup (org inventory convention).',
    )
    admin_confirmed_offer_display = models.CharField(
        max_length=32,
        blank=True,
        help_text='When set, overrides the AI-parsed offer for user-facing display (e.g. after admin review).',
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    @property
    def offer_display(self) -> str:
        if (self.admin_confirmed_offer_display or '').strip():
            return self.admin_confirmed_offer_display.strip()
        return format_share_bear_offer_display(self.quote_text)

    def __str__(self):
        return f'{self.user.username}: {self.item_name}'
