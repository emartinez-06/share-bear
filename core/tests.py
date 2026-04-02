import json
from unittest.mock import patch

from django.test import TestCase
from django.urls import reverse

from core.models import Order


class StripePaymentFlowTests(TestCase):
	def test_create_order_success(self):
		response = self.client.post(
			reverse('create-order'),
			data=json.dumps({'name': 'Test order', 'amount': '12.34'}),
			content_type='application/json',
		)

		self.assertEqual(response.status_code, 201)
		payload = response.json()
		self.assertIn('order_id', payload)

		order = Order.objects.get(id=payload['order_id'])
		self.assertEqual(order.status, 'pending')
		self.assertEqual(str(order.amount), '12.34')

	def test_create_order_invalid_amount(self):
		response = self.client.post(
			reverse('create-order'),
			data=json.dumps({'name': 'Test order', 'amount': '-1'}),
			content_type='application/json',
		)

		self.assertEqual(response.status_code, 400)

	@patch('core.views.stripe.PaymentIntent.create')
	def test_create_payment_intent_success(self, mock_create):
		mock_create.return_value = {
			'id': 'pi_test_123',
			'client_secret': 'pi_test_123_secret_abc',
		}
		order = Order.objects.create(name='Deposit', amount='45.00')

		response = self.client.post(reverse('create-payment-intent', args=[order.id]))

		self.assertEqual(response.status_code, 200)
		order.refresh_from_db()
		self.assertEqual(order.stripe_payment_intent, 'pi_test_123')
		self.assertEqual(response.json()['client_secret'], 'pi_test_123_secret_abc')

	@patch('core.views.stripe.Webhook.construct_event')
	def test_webhook_marks_order_paid(self, mock_construct_event):
		order = Order.objects.create(name='Deposit', amount='60.00')
		mock_construct_event.return_value = {
			'type': 'payment_intent.succeeded',
			'data': {'object': {'metadata': {'order_id': str(order.id)}}},
		}

		response = self.client.post(
			reverse('stripe-webhook'),
			data='{}',
			content_type='application/json',
			HTTP_STRIPE_SIGNATURE='t=123,v1=test',
		)

		self.assertEqual(response.status_code, 200)
		order.refresh_from_db()
		self.assertEqual(order.status, 'paid')

	@patch('core.views.stripe.Webhook.construct_event')
	def test_webhook_marks_order_failed(self, mock_construct_event):
		order = Order.objects.create(name='Deposit', amount='60.00')
		mock_construct_event.return_value = {
			'type': 'payment_intent.payment_failed',
			'data': {'object': {'metadata': {'order_id': str(order.id)}}},
		}

		response = self.client.post(
			reverse('stripe-webhook'),
			data='{}',
			content_type='application/json',
			HTTP_STRIPE_SIGNATURE='t=123,v1=test',
		)

		self.assertEqual(response.status_code, 200)
		order.refresh_from_db()
		self.assertEqual(order.status, 'failed')

	def test_webhook_rejects_missing_signature(self):
		response = self.client.post(
			reverse('stripe-webhook'),
			data='{}',
			content_type='application/json',
		)

		self.assertEqual(response.status_code, 400)
