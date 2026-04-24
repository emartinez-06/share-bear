from django.contrib import admin
from django.urls import include, path

from core.views import (
    admin_accept_quote_view,
    admin_quotes_view,
    ai_quote_dev_success_view,
    ai_quote_success_detail_view,
    ai_quote_view,
    home_view,
    quote_video_upload_view,
)

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', home_view, name='home'),
    path('ai-quote/', ai_quote_view, name='ai_quote'),
    path('ai-quote/dev-success/', ai_quote_dev_success_view, name='ai_quote_dev_success'),
    path('ai-quote/complete/<int:quote_id>/', ai_quote_success_detail_view, name='ai_quote_success_detail'),
    path('ai-quote/complete/<int:quote_id>/video/', quote_video_upload_view, name='quote_video_upload'),
    path('admin-quotes/', admin_quotes_view, name='admin_quotes'),
    path('admin-quotes/accept/<int:quote_id>/', admin_accept_quote_view, name='admin_accept_quote'),
    path('accounts/', include('users.urls')),
]
