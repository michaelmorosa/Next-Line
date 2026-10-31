from django.test import TestCase
from rest_framework.test import APIClient


class AccountFlowTests(TestCase):
    def test_sign_up_log_in_and_set_crash_contact(self):
        client = APIClient()
        res = client.post('/api/auth/users/', {
            'username': 'shredder', 'email': 'shred@example.com',
            'password': 'gnarly-line-42', 're_password': 'gnarly-line-42',
        }, format='json')
        self.assertEqual(res.status_code, 201, res.data)

        tokens = client.post('/api/auth/jwt/create/', {'username': 'shredder', 'password': 'gnarly-line-42'},
                             format='json').data
        refreshed = client.post('/api/auth/jwt/refresh/', {'refresh': tokens['refresh']}, format='json').data
        self.assertIn('refresh', refreshed)  # rotated; the app stores the new one

        client.credentials(HTTP_AUTHORIZATION=f"Bearer {refreshed['access']}")
        res = client.patch('/api/user/me/', {'crash_contact_name': 'Sam', 'crash_contact_phone': '+1 555 555 0123'},
                           format='json')
        self.assertEqual(res.status_code, 200, res.data)
        self.assertEqual(res.data['crash_contact_name'], 'Sam')

        bad = client.patch('/api/user/me/', {'crash_contact_phone': 'call me'}, format='json')
        self.assertEqual(bad.status_code, 400)

    def test_duplicate_email_rejected(self):
        client = APIClient()
        body = {'username': 'a', 'email': 'dup@example.com', 'password': 'gnarly-line-42', 're_password': 'gnarly-line-42'}
        client.post('/api/auth/users/', body, format='json')
        res = client.post('/api/auth/users/', {**body, 'username': 'b', 'email': 'DUP@example.com'}, format='json')
        self.assertEqual(res.status_code, 400)
