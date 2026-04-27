from datetime import date, datetime, timezone as dt_timezone
from types import SimpleNamespace
from unittest.mock import patch
from urllib.parse import unquote
from zoneinfo import ZoneInfo

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase, override_settings
from django.utils import timezone
from googleapiclient.errors import HttpError

from core.gemini_quote import extract_confidence_level, extract_share_bear_offer_amount, format_share_bear_offer_display
from core.forms import AIQuoteForm, AdminAcceptQuoteForm, normalize_confirmed_buyback_offer
from core.models import AIQuote
from core.views import build_approval_mailto_url, build_pickup_location_mailto_url


class ExtractOfferTests(TestCase):
    def test_line_with_labels(self):
        text = """
- Item confidence: HIGH
- Estimated retail (USD): $500
- SHARE Bear offer (USD): $150
- Notes / assumptions: Example.
""".strip()
        self.assertEqual(extract_share_bear_offer_amount(text), "$150")
        self.assertEqual(format_share_bear_offer_display(text), "$150")

    def test_second_amount_fallback(self):
        text = "Item confidence: HIGH\nRetail is about $400. The buy-back is $120."
        self.assertEqual(extract_share_bear_offer_amount(text), "$120")

    def test_single_amount(self):
        self.assertEqual(extract_share_bear_offer_amount("We can offer $99 total."), "$99")
        text_with_confidence = "Item confidence: HIGH\nWe can offer $99 total."
        self.assertEqual(format_share_bear_offer_display(text_with_confidence), "$30")

    def test_uncertain_phrase_with_amount_displays_zero(self):
        text = (
            "Item confidence: MEDIUM\n"
            "Estimated retail (USD): $450\n"
            "SHARE Bear offer (USD): $135\n"
            "Notes: There is insufficient information about condition, so this is uncertain."
        )
        self.assertEqual(format_share_bear_offer_display(text), "$0")

    def test_uncertain_phrase_without_amount_displays_zero(self):
        text = "Item confidence: MEDIUM\nUnable to estimate a fair value because there is not enough info."
        self.assertEqual(format_share_bear_offer_display(text), "$0")

    def test_confident_quote_still_displays_amount(self):
        text = (
            "Item confidence: HIGH\n"
            "Estimated retail (USD): $300\n"
            "SHARE Bear offer (USD): $90\n"
            "Notes: Typical market resale for this model in working condition."
        )
        self.assertEqual(format_share_bear_offer_display(text), "$90")

    def test_offer_is_recalculated_from_retail_when_model_offer_mismatches(self):
        text = (
            "Item confidence: HIGH\n"
            "Estimated retail (USD): $500\n"
            "SHARE Bear offer (USD): $45\n"
            "Notes: Example mismatch."
        )
        self.assertEqual(format_share_bear_offer_display(text), "$150")


class ConfidenceLevelTests(TestCase):
    def test_low_confidence_returns_zero(self):
        text = (
            "Item confidence: LOW\n"
            "Estimated retail (USD): $300\n"
            "SHARE Bear offer (USD): $90\n"
            "Notes: Cannot verify this is a real product."
        )
        self.assertEqual(extract_confidence_level(text), "LOW")
        self.assertEqual(format_share_bear_offer_display(text), "$0")

    def test_medium_confidence_returns_offer(self):
        text = (
            "Item confidence: MEDIUM\n"
            "Estimated retail (USD): $400\n"
            "SHARE Bear offer (USD): $120\n"
            "Notes: Item seems real but limited info."
        )
        self.assertEqual(extract_confidence_level(text), "MEDIUM")
        self.assertEqual(format_share_bear_offer_display(text), "$120")

    def test_high_confidence_returns_offer(self):
        text = (
            "Item confidence: HIGH\n"
            "Estimated retail (USD): $600\n"
            "SHARE Bear offer (USD): $180\n"
            "Notes: Recognizable product with verifiable market data."
        )
        self.assertEqual(extract_confidence_level(text), "HIGH")
        self.assertEqual(format_share_bear_offer_display(text), "$180")

    def test_missing_confidence_defaults_to_low(self):
        text = (
            "Estimated retail (USD): $500\n"
            "SHARE Bear offer (USD): $150\n"
            "Notes: No confidence line in response."
        )
        self.assertEqual(extract_confidence_level(text), "LOW")
        self.assertEqual(format_share_bear_offer_display(text), "$0")

    def test_confidence_case_insensitive(self):
        self.assertEqual(extract_confidence_level("Item confidence: high"), "HIGH")
        self.assertEqual(extract_confidence_level("Item confidence: Medium"), "MEDIUM")
        self.assertEqual(extract_confidence_level("Item confidence: low"), "LOW")


class AIQuoteFormValidationTests(TestCase):
    def test_rejects_gibberish_item_text(self):
        form = AIQuoteForm(
            data={
                "item_name": "fjsdfdsj",
                "description": "asdfghjkl qwrtyuiop",
                "make": "Apple",
                "model": "M3",
                "unknown_make_model": False,
            }
        )
        self.assertFalse(form.is_valid())
        self.assertIn("real item name", str(form.errors))

    def test_accepts_normal_item_text(self):
        form = AIQuoteForm(
            data={
                "item_name": "MacBook Pro 14",
                "description": "Used laptop in good condition with charger included.",
                "make": "Apple",
                "model": "M3 Pro",
                "unknown_make_model": False,
            }
        )
        self.assertTrue(form.is_valid())


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


class BuildApprovalMailtoUrlTests(TestCase):
    def test_mailto_contains_required_template_content(self):
        user = get_user_model().objects.create_user(
            'mailuser', 'mailuser@test.example', 'testpass123', first_name='Mia'
        )
        quote = AIQuote.objects.create(
            user=user,
            item_name='iPad Pro',
            description='11-inch model in good condition',
            quote_text='- SHARE Bear offer (USD): $100\n',
            admin_confirmed_offer_display='$125',
            quote_accepted_by_admin=True,
        )

        url = build_approval_mailto_url(quote)
        self.assertIsNotNone(url)
        decoded = unquote(url or '')
        self.assertIn('mailto:mailuser@test.example?subject=', decoded)
        self.assertIn('Your item has been approved!', decoded)
        self.assertIn('Final approved price: $125', decoded)
        self.assertIn('Item: iPad Pro', decoded)
        self.assertIn('Item description: 11-inch model in good condition', decoded)
        self.assertIn('reply directly to this email', decoded)

    def test_mailto_returns_none_without_recipient_email(self):
        user = get_user_model().objects.create_user('noemail', '', 'testpass123')
        quote = AIQuote.objects.create(
            user=user,
            item_name='Desk lamp',
            description='White desk lamp',
            quote_text='- SHARE Bear offer (USD): $20\n',
            quote_accepted_by_admin=True,
        )
        self.assertIsNone(build_approval_mailto_url(quote))


class BuildPickupLocationMailtoUrlTests(TestCase):
    def test_mailto_contains_pickup_location_prompt(self):
        user = get_user_model().objects.create_user(
            'pickupmail', 'pickupmail@test.example', 'testpass123', first_name='Pia'
        )
        quote = AIQuote.objects.create(
            user=user,
            item_name='Monitor',
            description='24-inch monitor',
            quote_text='- SHARE Bear offer (USD): $40\n',
            quote_accepted_by_admin=True,
            booking_initiated=True,
            google_event_id='evt_1',
            pickup_starts_at=timezone.now(),
        )
        url = build_pickup_location_mailto_url(quote)
        self.assertIsNotNone(url)
        decoded = unquote(url or '')
        self.assertIn('Pickup location confirmation needed', decoded)
        self.assertIn('Confirmed! You booked a pickup slot', decoded)
        self.assertIn('Off-campus apartment (include apartment number)', decoded)


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

    def test_approved_modal_renders_mailto_link(self):
        self.client.login(username='admstaff', password='testpass123')
        self.client.post(
            f'/admin-dashboard/approve/{self.quote.pk}/',
            {'final_offer': '125.50'},
        )
        r = self.client.get('/admin-dashboard/')
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, 'mailto:sel%40test.example?subject=')
        self.assertContains(r, 'Email user')

    def test_approved_modal_shows_email_missing_fallback(self):
        seller_no_email = get_user_model().objects.create_user(
            'sellernoemail', '', 'testpass123'
        )
        AIQuote.objects.create(
            user=seller_no_email,
            item_name='Chair',
            description='Wood chair',
            quote_text='- SHARE Bear offer (USD): $25\n',
            has_video=True,
            video_path='2/quote_22/x.mp4',
            quote_accepted_by_admin=True,
            quote_reviewed_at=timezone.now(),
        )
        self.client.login(username='admstaff', password='testpass123')
        r = self.client.get('/admin-dashboard/')
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, 'No account email on file for this user.')


class AdminAcceptQuoteFormTests(TestCase):
    def test_form_validates_final_offer(self):
        f = AdminAcceptQuoteForm({'final_offer': 'bad'})
        self.assertFalse(f.is_valid())
        f2 = AdminAcceptQuoteForm({'final_offer': '50'})
        self.assertTrue(f2.is_valid())
        self.assertEqual(f2.cleaned_data['final_offer'], '$50')


class AdminKanbanMetadataTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.staff = User.objects.create_user('kanbanstaff', 'ks@test.example', 'pw', is_staff=True)
        cls.seller = User.objects.create_user('kquote', 'kq@test.example', 'pw2')
        cls.quote = AIQuote.objects.create(
            user=cls.seller,
            item_name='Lamp',
            description='desk lamp',
            quote_text='- SHARE Bear offer (USD): $15\n',
            has_video=True,
            video_path='1/q/x.mp4',
            quote_accepted_by_admin=True,
        )

    def test_assign_admin_updates_quote(self):
        self.client.login(username='kanbanstaff', password='pw')
        r = self.client.post(
            f'/admin-dashboard/assign-admin/{self.quote.pk}/',
            {'assigned_admin_name': 'Emma'},
        )
        self.assertEqual(r.status_code, 302)
        self.quote.refresh_from_db()
        self.assertEqual(self.quote.assigned_admin_name, 'Emma')

    def test_pickup_label_updates_when_picked_up(self):
        self.quote.picked_up = True
        self.quote.picked_up_at = timezone.now()
        self.quote.save(update_fields=['picked_up', 'picked_up_at'])
        self.client.login(username='kanbanstaff', password='pw')
        r = self.client.post(
            f'/admin-dashboard/pickup-label/{self.quote.pk}/',
            {'pickup_label_color': 'blue', 'pickup_label_number': '7'},
        )
        self.assertEqual(r.status_code, 302)
        self.quote.refresh_from_db()
        self.assertEqual(self.quote.pickup_label_color, 'blue')
        self.assertEqual(self.quote.pickup_label_number, 7)


class ProfileAttachPickupViewTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.user = User.objects.create_user('pickup1', 'p1@t.e', 'pw1')
        cls.user2 = User.objects.create_user('other', 'o@t.e', 'pw2')
        cls.q_ok = AIQuote.objects.create(
            user=cls.user,
            item_name='Guitar',
            description='d',
            quote_text='- SHARE Bear offer (USD): $100\n',
            has_video=True,
            video_path='1/1/x',
            quote_accepted_by_admin=True,
        )
        cls.q_other = AIQuote.objects.create(
            user=cls.user2,
            item_name='Other',
            description='d',
            quote_text='- SHARE Bear offer (USD): $50\n',
            has_video=True,
            video_path='1/1/y',
            quote_accepted_by_admin=True,
        )

    @override_settings(
        GOOGLE_SERVICE_ACCOUNT_KEY_PATH='',
        GOOGLE_SLOT_SOURCE_CALENDAR_IDS=[],
    )
    def test_profile_without_calendar_config(self):
        self.client.login(username='pickup1', password='pw1')
        r = self.client.get('/accounts/profile/')
        self.assertEqual(r.status_code, 200)
        self.assertNotContains(r, 'Schedule pickup')

    @patch('users.views.is_pickup_calendar_configured', return_value=True)
    @patch('users.views.resolve_available_preset_slot')
    @patch('users.views.create_pickup_event')
    def test_attach_saves_event_ids(self, m_create, m_res, m_cfg):
        from datetime import datetime, timezone

        from core.google_calendar import make_slot_post_key

        st = datetime(2026, 6, 15, 15, 0, tzinfo=timezone.utc)
        en = datetime(2026, 6, 15, 15, 30, tzinfo=timezone.utc)
        m_res.return_value = (st, en)
        m_create.return_value = {
            'id': 'evt123',
            'htmlLink': 'https://calendar.google.com/calendar/event?e=abc',
        }
        self.client.login(username='pickup1', password='pw1')
        key = make_slot_post_key('cal@example.com', st, en)
        r = self.client.post(
            '/accounts/profile/pickup/attach/',
            {
                'slot_key': key,
                'quote_ids': [str(self.q_ok.pk)],
            },
        )
        self.assertEqual(r.status_code, 302)
        self.q_ok.refresh_from_db()
        self.assertEqual(self.q_ok.google_calendar_id, 'cal@example.com')
        self.assertEqual(self.q_ok.google_event_id, 'evt123')
        self.assertTrue(self.q_ok.booking_initiated)
        self.assertIn('calendar.google', self.q_ok.pickup_event_html_link)
        m_create.assert_called_once()

    @patch('users.views.is_pickup_calendar_configured', return_value=True)
    @patch('users.views.resolve_available_preset_slot')
    @patch('users.views.create_pickup_event')
    def test_cannot_attach_other_users_quote(
        self, m_create, m_res, m_cfg
    ):
        from datetime import datetime, timezone

        from core.google_calendar import make_slot_post_key

        st = datetime(2026, 6, 15, 15, 0, tzinfo=timezone.utc)
        en = datetime(2026, 6, 15, 15, 30, tzinfo=timezone.utc)
        m_res.return_value = (st, en)
        m_create.return_value = {
            'id': 'e',
            'htmlLink': 'https://x',
        }
        self.client.login(username='pickup1', password='pw1')
        r = self.client.post(
            '/accounts/profile/pickup/attach/',
            {
                'slot_key': make_slot_post_key('c@x', st, en),
                'quote_ids': [str(self.q_other.pk)],
            },
        )
        self.assertEqual(r.status_code, 302)
        self.q_other.refresh_from_db()
        self.assertEqual(self.q_other.google_event_id, '')

    @patch('users.views.is_pickup_calendar_configured', return_value=True)
    @patch('users.views.resolve_available_preset_slot')
    @patch('users.views.create_pickup_event')
    def test_attach_handles_calendar_runtime_error(self, m_create, m_res, m_cfg):
        from datetime import datetime, timezone

        from core.google_calendar import make_slot_post_key

        st = datetime(2026, 6, 15, 15, 0, tzinfo=timezone.utc)
        en = datetime(2026, 6, 15, 15, 30, tzinfo=timezone.utc)
        m_res.return_value = (st, en)
        m_create.side_effect = RuntimeError('invalid google credentials')
        self.client.login(username='pickup1', password='pw1')
        r = self.client.post(
            '/accounts/profile/pickup/attach/',
            {
                'slot_key': make_slot_post_key('c@x', st, en),
                'quote_ids': [str(self.q_ok.pk)],
            },
            follow=True,
        )
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, 'invalid google credentials')
        self.q_ok.refresh_from_db()
        self.assertEqual(self.q_ok.google_event_id, '')

    @override_settings(
        GOOGLE_SERVICE_ACCOUNT_KEY_PATH='',
        GOOGLE_SLOT_SOURCE_CALENDAR_IDS=[],
    )
    def test_attach_rejects_without_config(self):
        self.client.login(username='pickup1', password='pw1')
        r = self.client.post(
            '/accounts/profile/pickup/attach/',
            {
                'slot_key': 'a###b',
                'quote_ids': [str(self.q_ok.pk)],
            },
        )
        self.assertEqual(r.status_code, 302)
        self.q_ok.refresh_from_db()
        self.assertEqual(self.q_ok.google_event_id, '')


class PickupHourlySlotDefinitionTests(TestCase):
    @override_settings(
        PICKUP_WEEKLY_SLOT_DEFINITIONS=[
            {'weekday': 4, 'hourly': True, 'first': '09:00', 'last_start': '17:00'},
        ],
        GOOGLE_PICKUP_TIMEZONE='America/Chicago',
    )
    def test_friday_nine_one_hour_blocks(self):
        from core.google_calendar import _generate_all_preset_instances

        tmin = datetime(2026, 1, 1, 6, 0, tzinfo=dt_timezone.utc)
        tmax = datetime(2026, 1, 3, 6, 0, tzinfo=dt_timezone.utc)
        inst = _generate_all_preset_instances(time_min=tmin, time_max=tmax)
        friday = date(2026, 1, 2)
        tz = ZoneInfo('America/Chicago')
        on_friday = [p for p in inst if p[0].astimezone(tz).date() == friday]
        self.assertEqual(len(on_friday), 9)
        self.assertEqual(on_friday[0][0].astimezone(tz).hour, 9)
        self.assertEqual(on_friday[-1][0].astimezone(tz).hour, 17)

    @override_settings(
        PICKUP_WEEKLY_SLOT_DEFINITIONS=[
            {'weekday': 6, 'hourly': True, 'first': '12:00', 'last_start': '17:00'},
        ],
        GOOGLE_PICKUP_TIMEZONE='America/Chicago',
    )
    def test_sunday_six_one_hour_blocks(self):
        from core.google_calendar import _generate_all_preset_instances

        tmin = datetime(2026, 1, 3, 6, 0, tzinfo=dt_timezone.utc)
        tmax = datetime(2026, 1, 5, 6, 0, tzinfo=dt_timezone.utc)
        inst = _generate_all_preset_instances(time_min=tmin, time_max=tmax)
        sun = date(2026, 1, 4)
        tz = ZoneInfo('America/Chicago')
        on_sun = [p for p in inst if p[0].astimezone(tz).date() == sun]
        self.assertEqual(len(on_sun), 6)
        self.assertEqual(on_sun[0][0].astimezone(tz).hour, 12)
        self.assertEqual(on_sun[-1][0].astimezone(tz).hour, 17)


class GoogleCalendarCredentialConfigTests(TestCase):
    @override_settings(
        GOOGLE_SERVICE_ACCOUNT_KEY_JSON='{"type":"service_account","client_email":"svc@test.example"}',
        GOOGLE_SERVICE_ACCOUNT_KEY_PATH='',
        GOOGLE_SLOT_SOURCE_CALENDAR_IDS=['cal@example.com'],
    )
    def test_pickup_calendar_configured_with_json_env(self):
        from core.google_calendar import is_pickup_calendar_configured

        self.assertTrue(is_pickup_calendar_configured())

    @override_settings(
        GOOGLE_SERVICE_ACCOUNT_KEY_JSON='{"type":"service_account","client_email":"svc@test.example"}',
        GOOGLE_SERVICE_ACCOUNT_KEY_PATH='',
        GOOGLE_SLOT_SOURCE_CALENDAR_IDS=['cal@example.com'],
    )
    @patch('core.google_calendar.service_account.Credentials.from_service_account_info')
    def test_get_credentials_prefers_json_env(self, m_from_info):
        from core.google_calendar import _get_credentials

        m_from_info.return_value = object()
        creds = _get_credentials()
        self.assertIsNotNone(creds)
        m_from_info.assert_called_once()


class GoogleCalendarBookingErrorMappingTests(TestCase):
    @override_settings(
        GOOGLE_SERVICE_ACCOUNT_KEY_JSON='{"type":"service_account","client_email":"svc@test.example"}',
        GOOGLE_SLOT_SOURCE_CALENDAR_IDS=['sharebearhelp@gmail.com'],
    )
    @patch('core.google_calendar.get_calendar_service')
    def test_create_pickup_event_403_raises_permission_error(self, m_service):
        from datetime import datetime, timezone

        from core.google_calendar import create_pickup_event

        m_exec = m_service.return_value.events.return_value.insert.return_value.execute
        m_exec.side_effect = HttpError(SimpleNamespace(status=403, reason='Forbidden'), b'{}')

        with self.assertRaises(RuntimeError) as cm:
            create_pickup_event(
                'sharebearhelp@gmail.com',
                datetime(2026, 6, 15, 15, 0, tzinfo=timezone.utc),
                datetime(2026, 6, 15, 16, 0, tzinfo=timezone.utc),
                user_email='u@test.example',
                user_label='@u',
                quote_ids=[1],
                item_names=['Item'],
            )
        self.assertIn('permission denied', str(cm.exception).lower())
