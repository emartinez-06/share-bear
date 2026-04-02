import json
import logging
from decimal import Decimal, InvalidOperation

import stripe
from django.conf import settings
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, render
from django.views.decorators.csrf import csrf_exempt, ensure_csrf_cookie
from django.views.decorators.http import require_POST

from .models import Order

logger = logging.getLogger(__name__)

stripe.api_key = settings.STRIPE_SECRET_KEY


@ensure_csrf_cookie
def home_view(request):
    return render(
        request,
        'index.html',
        {
            'vercel_analytics_enabled': settings.VERCEL_ANALYTICS_ENABLED,
            'stripe_public_key': settings.STRIPE_PUBLIC_KEY,
        },
    )


@require_POST
def create_order(request):
    try:
        data = json.loads(request.body or '{}')
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON payload'}, status=400)

    name = str(data.get('name', '')).strip()
    amount_raw = str(data.get('amount', '')).strip()

    if not name:
        return JsonResponse({'error': 'Name is required'}, status=400)

    try:
        amount = Decimal(amount_raw).quantize(Decimal('0.01'))
    except (InvalidOperation, TypeError):
        return JsonResponse({'error': 'Amount must be a valid number'}, status=400)

    if amount <= 0:
        return JsonResponse({'error': 'Amount must be greater than 0'}, status=400)

    order = Order.objects.create(name=name, amount=amount)

    return JsonResponse(
        {
            'order_id': order.pk,
            'amount': str(order.amount),
            'status': order.status,
        },
        status=201,
    )


@require_POST
def create_payment_intent(request, order_id):
    order = get_object_or_404(Order, id=order_id)

    if order.status == 'paid':
        return JsonResponse({'error': 'Order is already paid'}, status=400)

    amount_cents = int(order.amount * 100)
    if amount_cents < 50:
        return JsonResponse({'error': 'Amount must be at least $0.50'}, status=400)

    try:
        intent = stripe.PaymentIntent.create(
            amount=amount_cents,
            currency='usd',
            metadata={'order_id': str(order.pk)},
        )
    except stripe.error.StripeError as exc:  # type: ignore
        logger.exception('Failed to create payment intent for order %s: %s', order.pk, exc)
        return JsonResponse({'error': 'Unable to create payment intent'}, status=502)

    order.stripe_payment_intent = intent['id']
    order.save(update_fields=['stripe_payment_intent'])

    return JsonResponse(
        {
            'client_secret': intent['client_secret'],
            'publishable_key': settings.STRIPE_PUBLIC_KEY,
        }
    )


@csrf_exempt
def stripe_webhook(request):
    payload = request.body
    sig_header = request.META.get('HTTP_STRIPE_SIGNATURE')

    if not sig_header:
        return JsonResponse({'error': 'Missing Stripe signature header'}, status=400)

    try:
        event = stripe.Webhook.construct_event(
            payload, sig_header, settings.STRIPE_WEBHOOK_SECRET
        )
    except ValueError:
        logger.warning('Stripe webhook received invalid JSON payload')
        return JsonResponse({'error': 'Invalid payload'}, status=400)
    except stripe.error.SignatureVerificationError:  # type: ignore
        logger.warning('Stripe webhook signature verification failed')
        return JsonResponse({'error': 'Invalid payload'}, status=400)

    event_type = event['type']
    intent = event['data']['object']
    metadata = intent.get('metadata', {})
    order_id = metadata.get('order_id')

    if event_type in {'payment_intent.succeeded', 'payment_intent.payment_failed'} and not order_id:
        logger.warning('Stripe webhook missing order_id metadata for event %s', event_type)
        return JsonResponse({'status': 'ignored'})

    if event_type == 'payment_intent.succeeded':
        updated = Order.objects.filter(id=order_id, status='pending').update(status='paid')
        if not updated:
            logger.info('No pending order updated for successful payment. order_id=%s', order_id)

    elif event_type == 'payment_intent.payment_failed':
        updated = Order.objects.filter(id=order_id, status='pending').update(status='failed')
        if not updated:
            logger.info('No pending order updated for failed payment. order_id=%s', order_id)

    return JsonResponse({'status': 'success'})