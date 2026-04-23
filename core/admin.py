from django.contrib import admin

from .models import AIQuote


@admin.register(AIQuote)
class AIQuoteAdmin(admin.ModelAdmin):
    list_display = ('item_name', 'user', 'created_at')
    search_fields = ('item_name', 'description', 'user__username')
    list_filter = ('created_at', 'unknown_make_model')
