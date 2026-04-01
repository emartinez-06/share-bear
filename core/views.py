from django.shortcuts import render
from django.conf import settings
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
import stripe
import json

from stripe.climate import Order


def home_view(request):
    return render(
        request,
        'index.html',
        {'vercel_analytics_enabled': settings.VERCEL_ANALYTICS_ENABLED},
    )

stripe.api_key = settings.STRIPE_SECRET_KEY

def create_payment_intent(request, order_id):
    order = Order.objects.get(id=order_id) # type: ignore
    
    intent = stripe.PaymentIntent.create(
        amount=int(order.amount * 100),  # Convert to cents
        currency='usd',
        metadata={'order_id': order.id}
    )
    
    order.stripe_payment_intent = intent['id']
    order.save()
    
    return JsonResponse({'client_secret': intent.client_secret})

@csrf_exempt
def stripe_webhook(request):
    payload = request.body
    sig_header = request.META['HTTP_STRIPE_SIGNATURE']

    try:
        event = stripe.Webhook.construct_event(
            payload, sig_header, settings.STRIPE_WEBHOOK_SECRET
        )
    except (ValueError, stripe.error.SignatureVerificationError): # type: ignore
        return JsonResponse({'error': 'Invalid payload'}, status=400)

    if event['type'] == 'payment_intent.succeeded':
        intent = event['data']['object']
        order_id = intent['metadata']['order_id']
        Order.objects.filter(id=order_id).update(status='paid') # type: ignore
    
    elif event['type'] == 'payment_intent.payment_failed':
        intent = event['data']['object']
        order_id = intent['metadata']['order_id']
        Order.objects.filter(id=order_id).update(status='failed') # type: ignore

    return JsonResponse({'status': 'success'})