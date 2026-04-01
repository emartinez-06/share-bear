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
