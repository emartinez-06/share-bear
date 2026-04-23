from django.contrib import admin
from django.urls import include, path

from core.views import ai_quote_view, home_view

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', home_view, name='home'),
    path('ai-quote/', ai_quote_view, name='ai_quote'),
    path('accounts/', include('users.urls')),
]
