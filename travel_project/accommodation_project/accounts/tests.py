import json

from django.test import SimpleTestCase


class FirebaseLoginEndpointTests(SimpleTestCase):
    def test_firebase_login_requires_id_token(self):
        response = self.client.post(
            "/api/auth/firebase-login/",
            data=json.dumps({"idToken": ""}),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertFalse(response.json()["success"])
