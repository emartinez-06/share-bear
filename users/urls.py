from django.urls import path

from . import views
from core.views import booking_initiate_view

urlpatterns = [
    path('signup/', views.signup_view, name='signup'),
    path('login/', views.login_view, name='login'),
    path('logout/', views.logout_view, name='logout'),
    path('profile/', views.profile_view, name='profile'),
    path('profile/pickup/attach/', views.profile_attach_pickup_view, name='profile_attach_pickup'),
    path('items/', views.user_items_view, name='user_items'),
    path('items/booking-initiate/', booking_initiate_view, name='booking_initiate'),
]
