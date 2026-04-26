from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase, override_settings

from core.gemini_quote import extract_share_bear_offer_amount, format_share_bear_offer_display
from core.forms import AdminAcceptQuoteForm, normalize_confirmed_buyback_offer
from core.models import AIQuote


class ExtractOfferTests(TestCase):
    def test_line_with_labels(self):
        text = """
- Estimated retail (USD): $500
- SHARE Bear offer (USD): $150
- Notes / assumptions: Example.
""".strip()
        self.assertEqual(extract_share_bear_offer_amount(text), "$150")
        self.assertEqual(format_share_bear_offer_display(text), "$150")

    def test_second_amount_fallback(self):
        text = "Retail is about $400. The buy-back is $120."
        self.assertEqual(extract_share_bear_offer_amount(text), "$120")

    def test_single_amount(self):
        self.assertEqual(extract_share_bear_offer_amount("We can offer $99 total."), "$99")


class DevSuccessPreviewTests(TestCase):
    def test_dev_success_disabled_returns_404(self):
        response = self.client.get('/ai-quote/dev-success/')
        self.assertEqual(response.status_code, 404)

    @override_settings(DEBUG=True)
    def test_dev_success_shows_with_debug(self):
        response = self.client.get('/ai-quote/dev-success/')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Sample item (dev preview)')
        self.assertContains(response, '$127')
        self.assertContains(response, 'Dev preview')
        self.assertContains(response, 'UI preview')
        self.assertContains(response, 'Upload video to accept this offer')


class NormalizeConfirmedOfferTests(TestCase):
    def test_empty_means_no_override(self):
        self.assertIsNone(normalize_confirmed_buyback_offer(''))
        self.assertIsNone(normalize_confirmed_buyback_offer('  $  '))

    def test_parses_variants(self):
        self.assertEqual(normalize_confirmed_buyback_offer('150'), '$150')
        self.assertEqual(normalize_confirmed_buyback_offer('$1,200'), '$1,200')
        self.assertEqual(normalize_confirmed_buyback_offer('99.50'), '$99.50')

    def test_invalid_raises(self):
        with self.assertRaises(ValidationError):
            normalize_confirmed_buyback_offer('not money')


class AIQuoteOfferDisplayTests(TestCase):
    def test_admin_override_wins(self):
        u = get_user_model().objects.create_user('o1', 'o1@t.example', 'p')
        q = AIQuote.objects.create(
            user=u,
            item_name='X',
            description='d',
            quote_text='- SHARE Bear offer (USD): $10\n',
            admin_confirmed_offer_display='  $200  ',
        )
        self.assertEqual(q.offer_display, '$200')


class AdminKanbanApproveViewTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.staff = User.objects.create_user(
            'admstaff', 'adm@test.example', 'testpass123', is_staff=True
        )
        cls.seller = User.objects.create_user('selleru', 'sel@test.example', 'testpass123')
        cls.quote = AIQuote.objects.create(
            user=cls.seller,
            item_name='Item A',
            description='d',
            quote_text='- SHARE Bear offer (USD): $100\n',
            has_video=True,
            video_path='1/quote_99/x.mp4',
        )

    def test_approve_non_staff_403(self):
        self.client.login(username='selleru', password='testpass123')
        r = self.client.post(
            f'/admin-dashboard/approve/{self.quote.pk}/',
            {'final_offer': '150'},
        )
        self.assertEqual(r.status_code, 403)

    def test_approve_with_price(self):
        self.client.login(username='admstaff', password='testpass123')
        r = self.client.post(
            f'/admin-dashboard/approve/{self.quote.pk}/',
            {'final_offer': '125.50'},
        )
        self.assertEqual(r.status_code, 302)
        self.quote.refresh_from_db()
        self.assertTrue(self.quote.quote_accepted_by_admin)
        self.assertIsNotNone(self.quote.quote_reviewed_at)
        self.assertEqual(self.quote.admin_confirmed_offer_display, '$125.50')

    def test_approve_invalid_price_no_change(self):
        self.client.login(username='admstaff', password='testpass123')
        r = self.client.post(
            f'/admin-dashboard/approve/{self.quote.pk}/',
            {'final_offer': 'xyz'},
        )
        self.assertEqual(r.status_code, 302)
        self.quote.refresh_from_db()
        self.assertFalse(self.quote.quote_accepted_by_admin)

    def test_approve_blank_uses_ai_offer_display_only(self):
        self.client.login(username='admstaff', password='testpass123')
        self.client.post(
            f'/admin-dashboard/approve/{self.quote.pk}/',
            {'final_offer': ''},
        )
        self.quote.refresh_from_db()
        self.assertTrue(self.quote.quote_accepted_by_admin)
        self.assertEqual(self.quote.admin_confirmed_offer_display, '')


class AdminAcceptQuoteFormTests(TestCase):
    def test_form_validates_final_offer(self):
        f = AdminAcceptQuoteForm({'final_offer': 'bad'})
        self.assertFalse(f.is_valid())
        f2 = AdminAcceptQuoteForm({'final_offer': '50'})
        self.assertTrue(f2.is_valid())
        self.assertEqual(f2.cleaned_data['final_offer'], '$50')
