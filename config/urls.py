from django.contrib import admin
from django.urls import path
from core import views

urlpatterns = [
    path('admin/', admin.site.urls),
    path('', views.home_view, name='home'),
    path('api/orders/', views.create_order, name='create-order'),
    path(
        'api/orders/<int:order_id>/payment-intent/',
        views.create_payment_intent,
        name='create-payment-intent',
    ),
    path('webhooks/stripe/', views.stripe_webhook, name='stripe-webhook'),
]
