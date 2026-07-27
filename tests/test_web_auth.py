import http.client
import json
import threading
import unittest
from datetime import timedelta

from xau_monitor.auth import AuthSession, AuthUser, utc_now
from xau_monitor.web import DashboardServer, make_handler


class FakeAuthStore:
    def __init__(self) -> None:
        self.session = None

    def get_session(self, raw_token):
        if raw_token == "valid-session":
            return AuthSession(
                user=AuthUser(id=1, username="owner"),
                raw_token=raw_token,
                expires_at=utc_now() + timedelta(days=1),
            )
        return None

    def authenticate(self, username, password, ip_address, user_agent):
        if username == "owner" and password == "valid-password-value":
            return AuthSession(
                user=AuthUser(id=1, username="owner"),
                raw_token="valid-session",
                expires_at=utc_now() + timedelta(days=1),
            )
        raise AssertionError("unexpected credentials")


class WebAuthenticationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.auth_store = FakeAuthStore()
        self.server = DashboardServer(
            ("127.0.0.1", 0),
            make_handler({}, self.auth_store),
        )
        self.thread = threading.Thread(
            target=self.server.serve_forever,
            daemon=True,
        )
        self.thread.start()
        self.connection = http.client.HTTPConnection(
            "127.0.0.1",
            self.server.server_port,
            timeout=5,
        )

    def tearDown(self) -> None:
        self.connection.close()
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)

    def test_login_page_is_public_but_dashboard_redirects(self) -> None:
        self.connection.request("GET", "/login")
        login_response = self.connection.getresponse()
        self.assertEqual(login_response.status, 200)
        login_response.read()

        self.connection.request("GET", "/")
        dashboard_response = self.connection.getresponse()
        self.assertEqual(dashboard_response.status, 303)
        self.assertEqual(dashboard_response.getheader("Location"), "/login")
        dashboard_response.read()

    def test_market_api_requires_session(self) -> None:
        self.connection.request("GET", "/api/snapshot?market=btc")
        response = self.connection.getresponse()
        payload = json.loads(response.read())
        self.assertEqual(response.status, 401)
        self.assertFalse(payload["ok"])

    def test_login_sets_host_only_secure_session_cookie(self) -> None:
        body = json.dumps(
            {
                "username": "owner",
                "password": "valid-password-value",
            }
        )
        self.connection.request(
            "POST",
            "/api/auth/login",
            body=body,
            headers={
                "Content-Type": "application/json",
                "Content-Length": str(len(body.encode("utf-8"))),
                "Origin": "http://127.0.0.1:8765",
            },
        )
        response = self.connection.getresponse()
        payload = json.loads(response.read())
        cookie = response.getheader("Set-Cookie")
        self.assertEqual(response.status, 200)
        self.assertTrue(payload["ok"])
        self.assertIn("__Host-sheshe_session=valid-session", cookie)
        self.assertIn("Secure", cookie)
        self.assertIn("HttpOnly", cookie)
        self.assertIn("SameSite=Strict", cookie)
        self.assertNotIn("Domain=", cookie)


if __name__ == "__main__":
    unittest.main()
