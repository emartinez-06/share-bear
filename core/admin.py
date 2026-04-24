from django.contrib import admin

from .gemini_quote import format_share_bear_offer_display
from .models import AIQuote


@admin.register(AIQuote)
class AIQuoteAdmin(admin.ModelAdmin):
    list_display = (
        'item_name',
        'offer',
        'has_video',
        'quote_accepted_by_admin',
        'user',
        'created_at',
    )
    search_fields = ('item_name', 'description', 'user__username')
    list_filter = ('created_at', 'unknown_make_model', 'has_video', 'quote_accepted_by_admin')
    readonly_fields = (
        'created_at',
        'offer',
        'quote_text',
        'video_path',
        'quote_reviewed_at',
    )

    @admin.display(description='Buy-back offer')
    def offer(self, obj):
        return format_share_bear_offer_display(obj.quote_text)
