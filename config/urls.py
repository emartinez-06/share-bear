from django.contrib import admin
from django.urls import include, path

from core.views import admin_quotes_view, ai_quote_view, home_view

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', home_view, name='home'),
    path('ai-quote/', ai_quote_view, name='ai_quote'),
    path('admin-quotes/', admin_quotes_view, name='admin_quotes'),
    path('accounts/', include('users.urls')),
]
