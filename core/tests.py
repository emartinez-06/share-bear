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

from core.gemini_quote import extract_share_bear_offer_amount, format_share_bear_offer_display
from core.forms import AdminAcceptQuoteForm, normalize_confirmed_buyback_offer
from core.models import AIQuote
from core.views import build_approval_mailto_url, build_pickup_location_mailto_url


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
        self.assertContains(response, 'sharebearhelp@gmail.com')


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

    def test_uses_legacy_placeholder_for_approved_items_without_assigned_admin(self):
        user = get_user_model().objects.create_user(
            'legacymail', 'legacymail@test.example', 'testpass123'
        )
        quote = AIQuote.objects.create(
            user=user,
            item_name='Legacy iPad',
            description='legacy item',
            quote_text='- SHARE Bear offer (USD): $75\n',
            quote_accepted_by_admin=True,
            assigned_admin_name='',
        )
        url = build_approval_mailto_url(quote)
        self.assertIsNotNone(url)
        self.assertIn('Erick', unquote(url or ''))


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
            assigned_admin_name='TestAdmin',
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


# ---------------------------------------------------------------------------
# Performance optimization tests
# ---------------------------------------------------------------------------

class AdminVideoUrlViewTests(TestCase):
    """Lazy video-URL endpoint used by JS to avoid N×Supabase calls on page load."""

    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.staff = User.objects.create_user(
            username='staffvid', email='staff@test.example', password='pw', is_staff=True,
        )
        cls.regular = User.objects.create_user(
            username='regularvid', email='user@test.example', password='pw',
        )
        cls.quote_with_video = AIQuote.objects.create(
            user=cls.staff,
            item_name='Laptop',
            description='desc',
            quote_text='$100',
            has_video=True,
            video_path='1/quote_1/current.mp4',
        )
        cls.quote_no_video = AIQuote.objects.create(
            user=cls.staff,
            item_name='Chair',
            description='desc',
            quote_text='$50',
            has_video=False,
        )

    def test_returns_signed_url_json_for_staff(self):
        self.client.login(username='staffvid', password='pw')
        with patch('core.views.create_signed_video_url', return_value='https://supabase.example/signed') as mock_sign:
            response = self.client.get(f'/admin-dashboard/video-url/{self.quote_with_video.pk}/')
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn('url', data)
        self.assertEqual(data['url'], 'https://supabase.example/signed')
        self.assertIn('mime', data)
        mock_sign.assert_called_once()

    def test_requires_staff_login(self):
        self.client.login(username='regularvid', password='pw')
        response = self.client.get(f'/admin-dashboard/video-url/{self.quote_with_video.pk}/')
        self.assertEqual(response.status_code, 403)

    def test_requires_authentication(self):
        response = self.client.get(f'/admin-dashboard/video-url/{self.quote_with_video.pk}/')
        self.assertEqual(response.status_code, 302)

    def test_quote_without_video_returns_404(self):
        self.client.login(username='staffvid', password='pw')
        response = self.client.get(f'/admin-dashboard/video-url/{self.quote_no_video.pk}/')
        self.assertEqual(response.status_code, 404)


class PickupSlotsViewTests(TestCase):
    """Lazy pickup-slots endpoint so user_items/profile page loads don't call Calendar API."""

    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.user = User.objects.create_user(
            username='slotsuser', email='slots@test.example', password='pw',
        )

    def test_returns_slots_json_when_authenticated(self):
        self.client.login(username='slotsuser', password='pw')
        fake_slots = [{'key': 'slot_abc', 'display': 'Mon 9-10 AM'}]
        with patch('users.views.list_candidate_slots', return_value=fake_slots):
            with patch('users.views.is_pickup_calendar_configured', return_value=True):
                response = self.client.get('/accounts/pickup-slots/')
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn('slots', data)
        self.assertEqual(data['slots'], fake_slots)

    def test_returns_empty_slots_when_calendar_not_configured(self):
        self.client.login(username='slotsuser', password='pw')
        with patch('users.views.is_pickup_calendar_configured', return_value=False):
            response = self.client.get('/accounts/pickup-slots/')
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data['slots'], [])

    def test_requires_authentication(self):
        response = self.client.get('/accounts/pickup-slots/')
        self.assertEqual(response.status_code, 302)


class AdminKanbanPerformanceTests(TestCase):
    """Kanban and admin-quotes page loads must NOT make any Supabase signed-URL calls."""

    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.staff = User.objects.create_user(
            username='staffkanban', email='sk@test.example', password='pw', is_staff=True,
        )
        AIQuote.objects.create(
            user=cls.staff, item_name='TV', description='d', quote_text='$80',
            has_video=True, video_path='1/quote_99/current.mp4',
        )

    def test_kanban_page_load_does_not_call_supabase(self):
        self.client.login(username='staffkanban', password='pw')
        with patch('core.views.create_signed_video_url') as mock_sign:
            response = self.client.get('/admin-dashboard/')
        self.assertEqual(response.status_code, 200)
        mock_sign.assert_not_called()

    def test_admin_quotes_page_load_does_not_call_supabase(self):
        self.client.login(username='staffkanban', password='pw')
        with patch('core.views.create_signed_video_url') as mock_sign:
            response = self.client.get('/admin-quotes/')
        self.assertEqual(response.status_code, 200)
        mock_sign.assert_not_called()


class UserItemsPerformanceTests(TestCase):
    """User items and profile page loads must NOT call the Google Calendar API."""

    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.user = User.objects.create_user(
            username='itemsperf', email='ip@test.example', password='pw',
        )

    def test_user_items_does_not_call_calendar_api_on_load(self):
        self.client.login(username='itemsperf', password='pw')
        with patch('users.views.list_candidate_slots') as mock_slots:
            response = self.client.get('/accounts/items/')
        self.assertEqual(response.status_code, 200)
        mock_slots.assert_not_called()

    def test_profile_does_not_call_calendar_api_on_load(self):
        self.client.login(username='itemsperf', password='pw')
        with patch('users.views.list_candidate_slots') as mock_slots:
            response = self.client.get('/accounts/profile/')
        self.assertEqual(response.status_code, 200)
        mock_slots.assert_not_called()


# ---------------------------------------------------------------------------
# Deny item feature
# ---------------------------------------------------------------------------

class AdminKanbanDenyViewTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.staff = User.objects.create_user('denystaff', 'ds@test.example', 'pw', is_staff=True)
        cls.seller = User.objects.create_user('denyseller', 'sell@test.example', 'pw2')
        cls.quote = AIQuote.objects.create(
            user=cls.seller,
            item_name='Old Lamp',
            description='Broken',
            quote_text='- SHARE Bear offer (USD): $5\n',
        )

    def test_deny_requires_staff(self):
        self.client.login(username='denyseller', password='pw2')
        r = self.client.post(
            f'/admin-dashboard/deny/{self.quote.pk}/',
            {'denial_reason': 'Not up to standard.'},
        )
        self.assertEqual(r.status_code, 403)

    def test_deny_sets_denied_flag_and_reason(self):
        self.client.login(username='denystaff', password='pw')
        r = self.client.post(
            f'/admin-dashboard/deny/{self.quote.pk}/',
            {'denial_reason': 'Item does not meet condition standards.'},
        )
        self.assertEqual(r.status_code, 302)
        self.quote.refresh_from_db()
        self.assertTrue(self.quote.denied)
        self.assertEqual(self.quote.denial_reason, 'Item does not meet condition standards.')

    def test_deny_with_blank_reason_still_sets_flag(self):
        self.client.login(username='denystaff', password='pw')
        self.client.post(f'/admin-dashboard/deny/{self.quote.pk}/', {'denial_reason': ''})
        self.quote.refresh_from_db()
        self.assertTrue(self.quote.denied)

    def test_undeny_clears_denied_flag(self):
        self.quote.denied = True
        self.quote.denial_reason = 'Old reason'
        self.quote.save(update_fields=['denied', 'denial_reason'])
        self.client.login(username='denystaff', password='pw')
        r = self.client.post(f'/admin-dashboard/undeny/{self.quote.pk}/')
        self.assertEqual(r.status_code, 302)
        self.quote.refresh_from_db()
        self.assertFalse(self.quote.denied)
        self.assertEqual(self.quote.denial_reason, '')

    def test_denied_items_in_denied_context_not_awaiting(self):
        self.quote.denied = True
        self.quote.save(update_fields=['denied'])
        self.client.login(username='denystaff', password='pw')
        r = self.client.get('/admin-dashboard/')
        self.assertEqual(r.status_code, 200)
        awaiting_ids = [q.pk for q in r.context['awaiting']]
        denied_ids = [q.pk for q in r.context['denied']]
        self.assertNotIn(self.quote.pk, awaiting_ids)
        self.assertIn(self.quote.pk, denied_ids)

    def test_kanban_context_has_denied_key(self):
        self.client.login(username='denystaff', password='pw')
        r = self.client.get('/admin-dashboard/')
        self.assertIn('denied', r.context)


class AdminKanbanUserGroupingTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.staff = User.objects.create_user('groupstaff', 'gs@test.example', 'pw', is_staff=True)
        cls.user_a = User.objects.create_user('groupuserA', 'ga@test.example', 'pw2')
        cls.user_b = User.objects.create_user('groupuserB', 'gb@test.example', 'pw3')
        AIQuote.objects.create(
            user=cls.user_a, item_name='Item A1', description='d', quote_text='$10',
        )
        AIQuote.objects.create(
            user=cls.user_a, item_name='Item A2', description='d', quote_text='$20',
        )
        AIQuote.objects.create(
            user=cls.user_b, item_name='Item B1', description='d', quote_text='$30',
        )

    def test_awaiting_by_user_contains_both_users(self):
        self.client.login(username='groupstaff', password='pw')
        r = self.client.get('/admin-dashboard/')
        self.assertEqual(r.status_code, 200)
        groups = r.context['awaiting_by_user']
        usernames = [g['user'].username for g in groups]
        self.assertIn('groupuserA', usernames)
        self.assertIn('groupuserB', usernames)

    def test_awaiting_by_user_groups_items_under_correct_user(self):
        self.client.login(username='groupstaff', password='pw')
        r = self.client.get('/admin-dashboard/')
        groups = r.context['awaiting_by_user']
        group_a = next(g for g in groups if g['user'].username == 'groupuserA')
        self.assertEqual(len(group_a['items']), 2)
        item_names = [q.item_name for q in group_a['items']]
        self.assertIn('Item A1', item_names)
        self.assertIn('Item A2', item_names)

    def test_awaiting_by_user_includes_item_count(self):
        self.client.login(username='groupstaff', password='pw')
        r = self.client.get('/admin-dashboard/')
        groups = r.context['awaiting_by_user']
        group_a = next(g for g in groups if g['user'].username == 'groupuserA')
        self.assertEqual(group_a['item_count'], 2)


class BuildVideoReminderMailtoUrlTests(TestCase):
    def test_builds_mailto_with_correct_content(self):
        from core.views import build_video_reminder_mailto_url
        user = get_user_model().objects.create_user(
            'vidremind', 'vr@test.example', 'pw', first_name='Sam'
        )
        quote = AIQuote.objects.create(
            user=user,
            item_name='Blender',
            description='High-speed blender',
            quote_text='- SHARE Bear offer (USD): $30\n',
            assigned_admin_name='Admin Sam',
        )
        url = build_video_reminder_mailto_url(quote)
        self.assertIsNotNone(url)
        decoded = unquote(url or '')
        self.assertIn('mailto:vr@test.example', decoded)
        self.assertIn('Blender', decoded)
        self.assertIn('upload', decoded.lower())

    def test_returns_none_when_admin_not_assigned(self):
        from core.views import build_video_reminder_mailto_url
        user = get_user_model().objects.create_user(
            'vidremind2', 'vr2@test.example', 'pw', first_name='Sam'
        )
        quote = AIQuote.objects.create(
            user=user,
            item_name='Blender',
            description='High-speed blender',
            quote_text='- SHARE Bear offer (USD): $30\n',
            assigned_admin_name='',
        )
        self.assertIsNone(build_video_reminder_mailto_url(quote))

    def test_returns_none_when_no_email(self):
        from core.views import build_video_reminder_mailto_url
        user = get_user_model().objects.create_user('noemailvr', '', 'pw')
        quote = AIQuote.objects.create(
            user=user, item_name='Lamp', description='d', quote_text='$5',
        )
        self.assertIsNone(build_video_reminder_mailto_url(quote))

    def test_video_reminder_url_attached_to_no_video_awaiting_items(self):
        User = get_user_model()
        User.objects.create_user('vstafftest', 'vs@test.example', 'pw', is_staff=True)
        seller = User.objects.create_user('vseller', 'vsel@test.example', 'pw2')
        q = AIQuote.objects.create(
            user=seller, item_name='Fan', description='d', quote_text='$15', has_video=False,
        )
        self.client.login(username='vstafftest', password='pw')
        r = self.client.get('/admin-dashboard/')
        self.assertEqual(r.status_code, 200)
        awaiting = r.context['awaiting']
        fan = next((x for x in awaiting if x.pk == q.pk), None)
        self.assertIsNotNone(fan)
        self.assertIsNone(fan.video_reminder_mailto_url)

    def test_video_reminder_url_attached_when_admin_is_assigned(self):
        User = get_user_model()
        User.objects.create_user('vstafftest3', 'vs3@test.example', 'pw', is_staff=True)
        seller = User.objects.create_user('vseller3', 'vsel3@test.example', 'pw2')
        q = AIQuote.objects.create(
            user=seller, item_name='Fan', description='d', quote_text='$15', has_video=False,
            assigned_admin_name='Case Owner',
        )
        self.client.login(username='vstafftest3', password='pw')
        r = self.client.get('/admin-dashboard/')
        awaiting = r.context['awaiting']
        fan = next((x for x in awaiting if x.pk == q.pk), None)
        self.assertIsNotNone(fan)
        self.assertIsNotNone(fan.video_reminder_mailto_url)

    def test_no_video_reminder_url_when_item_has_video(self):
        User = get_user_model()
        User.objects.create_user('vstafftest2', 'vs2@test.example', 'pw', is_staff=True)
        seller = User.objects.create_user('vseller2', 'vsel2@test.example', 'pw2')
        q = AIQuote.objects.create(
            user=seller, item_name='Mixer', description='d', quote_text='$20',
            has_video=True, video_path='1/q/x.mp4',
        )
        self.client.login(username='vstafftest2', password='pw')
        r = self.client.get('/admin-dashboard/')
        awaiting = r.context['awaiting']
        mixer = next((x for x in awaiting if x.pk == q.pk), None)
        self.assertIsNotNone(mixer)
        self.assertIsNone(mixer.video_reminder_mailto_url)


class DeniedItemsUserFacingTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.user = User.objects.create_user('denieduser', 'du@test.example', 'pw')
        cls.denied_quote = AIQuote.objects.create(
            user=cls.user,
            item_name='Cracked Phone',
            description='Screen cracked badly',
            quote_text='- SHARE Bear offer (USD): $10\n',
            denied=True,
            denial_reason='Item is too damaged for resale.',
        )
        cls.normal_quote = AIQuote.objects.create(
            user=cls.user,
            item_name='Headphones',
            description='Good condition',
            quote_text='- SHARE Bear offer (USD): $40\n',
        )

    def test_user_items_page_shows_denied_item_and_reason(self):
        self.client.login(username='denieduser', password='pw')
        r = self.client.get('/accounts/items/')
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, 'Cracked Phone')
        self.assertContains(r, 'Item is too damaged for resale.')

    def test_user_items_page_has_denied_quotes_context(self):
        self.client.login(username='denieduser', password='pw')
        r = self.client.get('/accounts/items/')
        self.assertIn('denied_quotes', r.context)
        denied_ids = [q.pk for q in r.context['denied_quotes']]
        self.assertIn(self.denied_quote.pk, denied_ids)
        self.assertNotIn(self.normal_quote.pk, denied_ids)


# ---------------------------------------------------------------------------
# Approved price display & running totals feature
# ---------------------------------------------------------------------------

class ParseOfferAmountTests(TestCase):
    def test_parses_whole_dollar(self):
        from core.gemini_quote import parse_offer_amount
        self.assertEqual(parse_offer_amount('$150'), 150.0)

    def test_parses_comma_separated(self):
        from core.gemini_quote import parse_offer_amount
        self.assertEqual(parse_offer_amount('$1,200'), 1200.0)

    def test_parses_cents(self):
        from core.gemini_quote import parse_offer_amount
        self.assertAlmostEqual(parse_offer_amount('$99.50'), 99.50)

    def test_returns_none_for_dash(self):
        from core.gemini_quote import parse_offer_amount
        self.assertIsNone(parse_offer_amount('—'))

    def test_returns_none_for_empty(self):
        from core.gemini_quote import parse_offer_amount
        self.assertIsNone(parse_offer_amount(''))

    def test_returns_none_for_non_numeric(self):
        from core.gemini_quote import parse_offer_amount
        self.assertIsNone(parse_offer_amount('Call for pricing'))


class FormatOffersTotalTests(TestCase):
    def test_sums_multiple_amounts(self):
        from core.gemini_quote import format_offers_total
        self.assertEqual(format_offers_total(['$100', '$200', '$50']), '$350')

    def test_returns_dash_when_none_parseable(self):
        from core.gemini_quote import format_offers_total
        self.assertEqual(format_offers_total(['—', '']), '—')

    def test_skips_unparseable_entries(self):
        from core.gemini_quote import format_offers_total
        self.assertEqual(format_offers_total(['$100', '—', '$50']), '$150')

    def test_formats_with_commas_for_large_totals(self):
        from core.gemini_quote import format_offers_total
        self.assertEqual(format_offers_total(['$1,000', '$500']), '$1,500')

    def test_formats_cents_when_total_is_fractional(self):
        from core.gemini_quote import format_offers_total
        self.assertEqual(format_offers_total(['$99.50', '$1.25']), '$100.75')

    def test_empty_list_returns_dash(self):
        from core.gemini_quote import format_offers_total
        self.assertEqual(format_offers_total([]), '—')


class ApprovedKanbanGroupTotalTests(TestCase):
    """Approved user cards on the kanban include a total_display field."""

    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.staff = User.objects.create_user('totstaff', 'ts@test.example', 'pw', is_staff=True)
        cls.seller = User.objects.create_user('totseller', 'tsel@test.example', 'pw2')
        cls.q1 = AIQuote.objects.create(
            user=cls.seller, item_name='Laptop', description='d',
            quote_text='- SHARE Bear offer (USD): $200\n',
            has_video=True, video_path='1/q/x.mp4',
            quote_accepted_by_admin=True, quote_reviewed_at=timezone.now(),
            admin_confirmed_offer_display='$200',
        )
        cls.q2 = AIQuote.objects.create(
            user=cls.seller, item_name='Phone', description='d',
            quote_text='- SHARE Bear offer (USD): $100\n',
            has_video=True, video_path='1/q/y.mp4',
            quote_accepted_by_admin=True, quote_reviewed_at=timezone.now(),
            admin_confirmed_offer_display='$100',
        )

    def test_approved_group_has_total_display(self):
        self.client.login(username='totstaff', password='pw')
        r = self.client.get('/admin-dashboard/')
        self.assertEqual(r.status_code, 200)
        groups = r.context['approved_by_user']
        seller_group = next(g for g in groups if g['user'].username == 'totseller')
        self.assertIn('total_display', seller_group)

    def test_approved_group_total_sums_items(self):
        self.client.login(username='totstaff', password='pw')
        r = self.client.get('/admin-dashboard/')
        groups = r.context['approved_by_user']
        seller_group = next(g for g in groups if g['user'].username == 'totseller')
        self.assertEqual(seller_group['total_display'], '$300')

    def test_kanban_approved_card_renders_total(self):
        self.client.login(username='totstaff', password='pw')
        r = self.client.get('/admin-dashboard/')
        self.assertContains(r, '$300')

    def test_kanban_approved_item_shows_price(self):
        """Each item row in the Approved column shows offer_display."""
        self.client.login(username='totstaff', password='pw')
        r = self.client.get('/admin-dashboard/')
        content = r.content.decode()
        self.assertIn('$200', content)
        self.assertIn('$100', content)


class UserItemsApprovedTotalTests(TestCase):
    """User items page shows a running total of approved items."""

    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.user = User.objects.create_user('runtotal', 'rt@test.example', 'pw')
        cls.q_approved1 = AIQuote.objects.create(
            user=cls.user, item_name='Monitor', description='d',
            quote_text='- SHARE Bear offer (USD): $80\n',
            has_video=True, video_path='1/q/a.mp4',
            quote_accepted_by_admin=True, quote_reviewed_at=timezone.now(),
            admin_confirmed_offer_display='$80',
        )
        cls.q_approved2 = AIQuote.objects.create(
            user=cls.user, item_name='Keyboard', description='d',
            quote_text='- SHARE Bear offer (USD): $40\n',
            has_video=True, video_path='1/q/b.mp4',
            quote_accepted_by_admin=True, quote_reviewed_at=timezone.now(),
            admin_confirmed_offer_display='$40',
        )
        cls.q_pending = AIQuote.objects.create(
            user=cls.user, item_name='Pending Item', description='d',
            quote_text='- SHARE Bear offer (USD): $50\n',
        )

    def test_user_items_context_has_approved_running_total(self):
        self.client.login(username='runtotal', password='pw')
        r = self.client.get('/accounts/items/')
        self.assertEqual(r.status_code, 200)
        self.assertIn('approved_running_total', r.context)

    def test_user_items_approved_running_total_value(self):
        self.client.login(username='runtotal', password='pw')
        r = self.client.get('/accounts/items/')
        self.assertEqual(r.context['approved_running_total'], '$120')

    def test_user_items_page_renders_approved_total(self):
        self.client.login(username='runtotal', password='pw')
        r = self.client.get('/accounts/items/')
        self.assertContains(r, '$120')

    def test_user_items_total_excludes_pending_items(self):
        self.client.login(username='runtotal', password='pw')
        r = self.client.get('/accounts/items/')
        self.assertEqual(r.context['approved_running_total'], '$120')


class BuildGroupLocationMailtoUrlTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user('grploc', 'grploc@test.example', 'pw', first_name='Sam')
        self.user_no_email = User.objects.create_user('grplocnoe', '', 'pw')
        self.booked_q = AIQuote.objects.create(
            user=self.user, item_name='Guitar', description='d',
            quote_text='$100', has_video=True, video_path='1/q/x',
            quote_accepted_by_admin=True, booking_initiated=True,
        )
        self.booked_q2 = AIQuote.objects.create(
            user=self.user, item_name='Amp', description='d',
            quote_text='$80', has_video=True, video_path='1/q/y',
            quote_accepted_by_admin=True, booking_initiated=True,
        )

    def test_returns_none_without_user_email(self):
        from core.views import build_group_location_mailto_url
        self.assertIsNone(build_group_location_mailto_url(self.user_no_email, [self.booked_q], admin_name='Erick'))

    def test_returns_none_without_booked_items(self):
        from core.views import build_group_location_mailto_url
        self.assertIsNone(build_group_location_mailto_url(self.user, [], admin_name='Erick'))

    def test_returns_none_without_assigned_admin(self):
        from core.views import build_group_location_mailto_url
        self.assertIsNone(build_group_location_mailto_url(self.user, [self.booked_q], admin_name=''))

    def test_contains_admin_check_booking_time_placeholder(self):
        from urllib.parse import unquote
        from core.views import build_group_location_mailto_url
        url = build_group_location_mailto_url(self.user, [self.booked_q], admin_name='Erick')
        self.assertIn('ADMIN CHECK BOOKING TIME', unquote(url or ''))

    def test_contains_pickup_fee_info(self):
        from urllib.parse import unquote
        from core.views import build_group_location_mailto_url
        url = build_group_location_mailto_url(self.user, [self.booked_q], admin_name='Erick')
        decoded = unquote(url or '')
        self.assertIn('$15', decoded)
        self.assertIn('Lot 25', decoded)

    def test_lists_all_booked_item_names(self):
        from urllib.parse import unquote
        from core.views import build_group_location_mailto_url
        url = build_group_location_mailto_url(self.user, [self.booked_q, self.booked_q2], admin_name='Erick')
        decoded = unquote(url or '')
        self.assertIn('Guitar', decoded)
        self.assertIn('Amp', decoded)

    def test_location_email_has_admin_in_subject(self):
        from urllib.parse import unquote
        from core.views import build_group_location_mailto_url
        url = build_group_location_mailto_url(self.user, [self.booked_q], admin_name='Erick')
        decoded = unquote(url or '')
        self.assertIn('subject=Pickup location needed for your SHARE Bear item(s) — Erick', decoded)

    def test_kanban_approved_card_shows_location_button_when_booked(self):
        User = get_user_model()
        staff = User.objects.create_user('grplocstaff', 'gs@test.example', 'pw', is_staff=True)
        self.client.login(username='grplocstaff', password='pw')
        r = self.client.get('/admin-dashboard/')
        self.assertContains(r, 'Email for pickup location')

    def test_kanban_approved_card_no_location_button_without_booking(self):
        User = get_user_model()
        staff = User.objects.create_user('grplocstaff2', 'gs2@test.example', 'pw', is_staff=True)
        unbooked_user = User.objects.create_user('grplocunbooked', 'ub@test.example', 'pw2')
        AIQuote.objects.create(
            user=unbooked_user, item_name='Desk', description='d', quote_text='$50',
            has_video=True, video_path='1/q/z', quote_accepted_by_admin=True,
            booking_initiated=False,
        )
        self.client.login(username='grplocstaff2', password='pw')
        r = self.client.get('/admin-dashboard/')
        # The unbooked user's card should not show the location button
        groups = r.context['approved_by_user']
        unbooked_group = next((g for g in groups if g['user'].username == 'grplocunbooked'), None)
        self.assertIsNotNone(unbooked_group)
        self.assertIsNone(unbooked_group.get('location_mailto_url'))


class KanbanGroupEmailButtonsTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.staff = User.objects.create_user('grpbtnstaff', 'gbs@test.example', 'pw', is_staff=True)
        cls.approved_user = User.objects.create_user('grpapproved', 'ga@test.example', 'pw2')
        cls.awaiting_only_user = User.objects.create_user('grpawait', 'gw@test.example', 'pw3')

        AIQuote.objects.create(
            user=cls.approved_user, item_name='Approved 1', description='d', quote_text='$100',
            has_video=True, video_path='1/a/x.mp4', quote_accepted_by_admin=True, assigned_admin_name='Erick',
        )
        AIQuote.objects.create(
            user=cls.approved_user, item_name='Approved 2', description='d', quote_text='$80',
            has_video=True, video_path='1/a/y.mp4', quote_accepted_by_admin=True, assigned_admin_name='Erick',
        )
        AIQuote.objects.create(
            user=cls.awaiting_only_user, item_name='Needs Video', description='d', quote_text='$30',
            has_video=False, assigned_admin_name='Erick',
        )

    def test_approved_group_has_group_approval_email_button(self):
        self.client.login(username='grpbtnstaff', password='pw')
        r = self.client.get('/admin-dashboard/')
        self.assertContains(r, 'Email approval + booking')

    def test_awaiting_group_has_video_update_email_when_no_approved_items(self):
        self.client.login(username='grpbtnstaff', password='pw')
        r = self.client.get('/admin-dashboard/')
        self.assertContains(r, 'Email video update request')

    def test_backfills_legacy_approved_assigned_admin_to_erick(self):
        User = get_user_model()
        legacy_user = User.objects.create_user('legacyapproved', 'la@test.example', 'pw4')
        quote = AIQuote.objects.create(
            user=legacy_user, item_name='Legacy Approved', description='d', quote_text='$50',
            has_video=True, video_path='1/l/z.mp4', quote_accepted_by_admin=True, assigned_admin_name='',
        )
        self.client.login(username='grpbtnstaff', password='pw')
        self.client.get('/admin-dashboard/')
        quote.refresh_from_db()
        self.assertEqual(quote.assigned_admin_name, 'Erick')

    def test_approved_group_email_button_shows_even_with_denied_items(self):
        User = get_user_model()
        mixed_user = User.objects.create_user('grpmixed', 'gm@test.example', 'pw5')
        AIQuote.objects.create(
            user=mixed_user, item_name='Approved Mixed', description='d', quote_text='$60',
            has_video=True, video_path='1/m/a.mp4', quote_accepted_by_admin=True, assigned_admin_name='Erick',
        )
        AIQuote.objects.create(
            user=mixed_user, item_name='Denied Mixed', description='d', quote_text='$10',
            denied=True,
        )
        self.client.login(username='grpbtnstaff', password='pw')
        r = self.client.get('/admin-dashboard/')
        self.assertEqual(r.status_code, 200)
        groups = r.context['approved_by_user']
        mixed_group = next((g for g in groups if g['user'].username == 'grpmixed'), None)
        self.assertIsNotNone(mixed_group)
        self.assertIsNotNone(mixed_group.get('approval_mailto_url'))


class GroupEmailSubjectAdminTests(TestCase):
    def test_booking_email_has_admin_in_subject_not_signature(self):
        from core.views import build_group_approval_mailto_url
        User = get_user_model()
        user = User.objects.create_user('booksubj', 'booksubj@test.example', 'pw')
        q = AIQuote.objects.create(
            user=user, item_name='Camera', description='d', quote_text='$100',
            quote_accepted_by_admin=True, assigned_admin_name='Erick',
        )
        url = build_group_approval_mailto_url(user, [q], admin_name='Erick')
        decoded = unquote(url or '')
        self.assertIn('subject=Your SHARE Bear items are approved — complete booking — Erick', decoded)
        self.assertNotIn('SHARE Bear Admin Team (Erick)', decoded)

    def test_video_email_has_admin_in_subject_not_signature(self):
        from core.views import build_group_video_reminder_mailto_url
        User = get_user_model()
        user = User.objects.create_user('vidsubj', 'vidsubj@test.example', 'pw')
        q = AIQuote.objects.create(
            user=user, item_name='Speaker', description='d', quote_text='$40',
            has_video=False, assigned_admin_name='Erick',
        )
        url = build_group_video_reminder_mailto_url(user, [q], admin_name='Erick')
        decoded = unquote(url or '')
        self.assertIn('subject=Action needed: upload video(s) for your SHARE Bear items — Erick', decoded)
        self.assertNotIn('SHARE Bear Admin Team (Erick)', decoded)
