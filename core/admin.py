from django.contrib import admin

from .models import AIQuote, Listing, ListingImage


@admin.register(AIQuote)
class AIQuoteAdmin(admin.ModelAdmin):
    list_display = (
        'item_name',
        'offer',
        'has_video',
        'quote_accepted_by_admin',
        'assigned_admin_name',
        'pickup_label_color',
        'pickup_label_number',
        'google_event_short',
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
        'admin_confirmed_offer_display',
        'google_calendar_id',
        'google_event_id',
        'pickup_event_html_link',
        'pickup_starts_at',
        'pickup_ends_at',
    )

    @admin.display(description='Buy-back offer')
    def offer(self, obj):
        return obj.offer_display

    @admin.display(description='GCal event', ordering='google_event_id')
    def google_event_short(self, obj):
        if not (obj.google_event_id or '').strip():
            return '—'
        s = (obj.google_event_id or '')[:20]
        return f'{s}…' if len(obj.google_event_id) > 20 else s


class ListingImageInline(admin.TabularInline):
    model = ListingImage
    extra = 0


@admin.register(Listing)
class ListingAdmin(admin.ModelAdmin):
    list_display = (
        'title',
        'price',
        'quantity',
        'status',
        'condition',
        'source_quote',
        'created_at',
    )
    search_fields = ('title', 'description', 'category')
    list_filter = ('status', 'condition', 'category', 'created_at')
    readonly_fields = ('created_at',)
    inlines = [ListingImageInline]
