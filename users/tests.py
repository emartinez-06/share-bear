import re

from django.contrib.auth import get_user_model
from django.test import TestCase

from .forms import SignupForm


class SignupFormValidationTests(TestCase):
    def _valid_data(self, **overrides):
        data = {
            'first_name': 'Alex',
            'last_name': 'Johnson',
            'username': 'alexj',
            'email': 'alexj@baylor.edu',
            'graduation_year': '2027',
            'password1': 'StrongPass123!',
            'password2': 'StrongPass123!',
        }
        data.update(overrides)
        return data

    def test_baylor_edu_email_accepted(self):
        form = SignupForm(data=self._valid_data())
        self.assertTrue(form.is_valid(), form.errors)

    def test_baylor_edu_uppercase_domain_accepted(self):
        form = SignupForm(data=self._valid_data(email='alexj@Baylor.edu'))
        self.assertTrue(form.is_valid(), form.errors)

    def test_non_baylor_email_rejected(self):
        form = SignupForm(data=self._valid_data(email='alexj@gmail.com'))
        self.assertFalse(form.is_valid())
        self.assertIn('email', form.errors)

    def test_baylor_com_domain_rejected(self):
        form = SignupForm(data=self._valid_data(email='alexj@baylor.com'))
        self.assertFalse(form.is_valid())
        self.assertIn('email', form.errors)

    def test_duplicate_email_rejected(self):
        User = get_user_model()
        User.objects.create_user(
            username='existinguser',
            email='taken@baylor.edu',
            password='testpass123',
        )
        form = SignupForm(data=self._valid_data(username='newuser', email='taken@baylor.edu'))
        self.assertFalse(form.is_valid())
        self.assertIn('email', form.errors)

    def test_duplicate_email_case_insensitive_rejected(self):
        User = get_user_model()
        User.objects.create_user(
            username='existinguser2',
            email='taken2@baylor.edu',
            password='testpass123',
        )
        form = SignupForm(data=self._valid_data(username='newuser2', email='TAKEN2@BAYLOR.EDU'))
        self.assertFalse(form.is_valid())
        self.assertIn('email', form.errors)


class UserModelTests(TestCase):
    def setUp(self):
        self.user_model = get_user_model()

    def test_regular_user_defaults(self):
        user = self.user_model.objects.create_user(
            username='bearstudent',
            password='testpass123',
        )

        self.assertFalse(user.is_staff)
        self.assertFalse(user.is_superuser)
        self.assertIsNone(user.graduation_year)

    def test_staff_user_is_not_superuser(self):
        user = self.user_model.objects.create_user(
            username='operationsadmin',
            password='testpass123',
            is_staff=True,
        )

        self.assertTrue(user.is_staff)
        self.assertFalse(user.is_superuser)

    def test_superuser_has_full_admin_flags(self):
        user = self.user_model.objects.create_superuser(
            username='platformowner',
            password='testpass123',
        )

        self.assertTrue(user.is_staff)
        self.assertTrue(user.is_superuser)


class AuthFlowTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user_model = get_user_model()

    def test_signup_creates_account_and_logs_user_in(self):
        response = self.client.post(
            '/accounts/signup/',
            {
                'first_name': 'Alex',
                'last_name': 'Johnson',
                'username': 'alexj',
                'email': 'alexj@baylor.edu',
                'graduation_year': '2027',
                'password1': 'StrongPass123!',
                'password2': 'StrongPass123!',
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, '/')
        self.assertTrue(self.user_model.objects.filter(username='alexj').exists())
        self.assertIn('_auth_user_id', self.client.session)

    def test_login_authenticates_existing_user(self):
        self.user_model.objects.create_user(
            username='signinuser',
            email='signin@test.example',
            password='testpass123',
        )
        response = self.client.post(
            '/accounts/login/',
            {'username': 'signinuser', 'password': 'testpass123'},
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, '/')
        self.assertIn('_auth_user_id', self.client.session)

    def test_logout_clears_session(self):
        self.user_model.objects.create_user(
            username='logoutuser',
            email='logout@test.example',
            password='testpass123',
        )
        self.client.login(username='logoutuser', password='testpass123')
        response = self.client.post('/accounts/logout/')
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, '/')
        self.assertNotIn('_auth_user_id', self.client.session)

    def test_logout_get_not_allowed(self):
        response = self.client.get('/accounts/logout/')
        self.assertEqual(response.status_code, 405)

    def test_user_items_page_shows_logout_for_authenticated_user(self):
        self.user_model.objects.create_user(
            username='itemsuser',
            email='items@test.example',
            password='testpass123',
        )
        self.client.login(username='itemsuser', password='testpass123')
        response = self.client.get('/accounts/items/')
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Log out')
        self.assertContains(response, "action=\"/accounts/logout/\"")


class MobileNavTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = get_user_model().objects.create_user(
            username='mobileuser',
            email='mobile@baylor.edu',
            password='testpass123',
        )

    def _logout_hidden_pattern(self, content: str) -> bool:
        """Returns True if the logout form uses the mobile-hiding 'hidden sm:inline' class."""
        return bool(re.search(r'action="/accounts/logout/"[^>]*class="hidden\s+sm:inline"', content))

    def test_home_page_has_single_mobile_bottom_nav(self):
        response = self.client.get('/')
        content = response.content.decode()
        self.assertEqual(content.count('id="mobile-bottom-nav"'), 1,
                         'Expected exactly one mobile-bottom-nav; found a duplicate.')

    def test_home_page_logout_not_hidden_on_mobile(self):
        self.client.login(username='mobileuser', password='testpass123')
        response = self.client.get('/')
        self.assertFalse(
            self._logout_hidden_pattern(response.content.decode()),
            'Logout form uses "hidden sm:inline" — it will be invisible on mobile viewports.',
        )

    def test_user_items_logout_not_hidden_on_mobile(self):
        self.client.login(username='mobileuser', password='testpass123')
        response = self.client.get('/accounts/items/')
        self.assertFalse(
            self._logout_hidden_pattern(response.content.decode()),
            'Logout form uses "hidden sm:inline" — it will be invisible on mobile viewports.',
        )

    def test_profile_logout_not_hidden_on_mobile(self):
        self.client.login(username='mobileuser', password='testpass123')
        response = self.client.get('/accounts/profile/')
        self.assertFalse(
            self._logout_hidden_pattern(response.content.decode()),
            'Logout form uses "hidden sm:inline" — it will be invisible on mobile viewports.',
        )
