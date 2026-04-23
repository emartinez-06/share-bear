from django.conf import settings
from django.db import models


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
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.user.username}: {self.item_name}'
