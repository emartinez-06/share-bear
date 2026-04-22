from django.contrib import admin
from django.urls import include, path

from core.views import home_view

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', home_view, name='home'),
    path('accounts/', include('users.urls')),
]
