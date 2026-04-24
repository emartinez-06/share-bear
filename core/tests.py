from django.test import TestCase, override_settings

from core.gemini_quote import extract_share_bear_offer_amount, format_share_bear_offer_display


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
