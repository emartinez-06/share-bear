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
        help_text='True when the user uploaded an acceptance/condition video.',
    )
    video_path = models.CharField(
        max_length=1024,
        blank=True,
        help_text='Object path in Supabase Storage (quote-videos bucket).',
    )
    quote_accepted_by_admin = models.BooleanField(
        default=False,
        help_text='Set when an admin has reviewed the video and accepted the buy-back offer.',
    )
    quote_reviewed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    @property
    def offer_display(self) -> str:
        return format_share_bear_offer_display(self.quote_text)

    def __str__(self):
        return f'{self.user.username}: {self.item_name}'
