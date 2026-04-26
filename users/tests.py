from django.contrib.auth import get_user_model
from django.test import TestCase


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
                'email': 'alexj@test.example',
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
