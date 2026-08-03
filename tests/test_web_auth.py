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


class FakeHypothesisStore:
    def dashboard(self, market, days):
        now = utc_now()
        return {
            "market": market,
            "days": days,
            "generated_at": now,
            "coverage": {
                "total_candles": 100,
                "first_opened_at": now,
                "last_opened_at": now,
            },
            "evidence": {"code": "collecting", "label": "采集中"},
            "summary": {},
            "anchors": [],
            "recent": [
                {
                    "event_at": now,
                    "minute": 30,
                    "chart_candles": [
                        {
                            "opened_at": now,
                            "open": 4000.0,
                            "high": 4001.0,
                            "low": 3999.0,
                            "close": 4000.5,
                        }
                    ],
                }
            ],
        }


class WebAuthenticationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.auth_store = FakeAuthStore()
        self.hypothesis_store = FakeHypothesisStore()
        self.server = DashboardServer(
            ("127.0.0.1", 0),
            make_handler(
                {"xau": object(), "btc": object()},
                self.auth_store,
                hypothesis_store=self.hypothesis_store,
            ),
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

        headers = {"Cookie": "__Host-sheshe_session=valid-session"}
        self.connection.request("GET", "/", headers=headers)
        dashboard_response = self.connection.getresponse()
        self.assertEqual(dashboard_response.status, 200)
        self.assertIn("猜想实时条件", dashboard_response.read().decode("utf-8"))

    def test_market_api_requires_session(self) -> None:
        for path in (
            "/api/snapshot?market=btc",
            "/api/bot/strategy-stats?market=xau&chat_id=test",
            "/api/hypotheses/reversal?market=xau&days=30",
        ):
            with self.subTest(path=path):
                self.connection.request("GET", path)
                response = self.connection.getresponse()
                payload = json.loads(response.read())
                self.assertEqual(response.status, 401)
                self.assertFalse(payload["ok"])

    def test_hypothesis_page_and_api_require_and_accept_session(self) -> None:
        self.connection.request("GET", "/hypotheses")
        redirect = self.connection.getresponse()
        self.assertEqual(redirect.status, 303)
        redirect.read()

        headers = {"Cookie": "__Host-sheshe_session=valid-session"}
        self.connection.request("GET", "/hypotheses", headers=headers)
        page = self.connection.getresponse()
        self.assertEqual(page.status, 200)
        self.assertIn("策略猜想", page.read().decode("utf-8"))

        self.connection.request(
            "GET",
            "/api/hypotheses/reversal?market=xau&days=30",
            headers=headers,
        )
        response = self.connection.getresponse()
        payload = json.loads(response.read())
        self.assertEqual(response.status, 200)
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["coverage"]["total_candles"], 100)
        self.assertEqual(payload["recent"][0]["minute"], 30)
        self.assertIsInstance(
            payload["recent"][0]["chart_candles"][0]["opened_at"],
            str,
        )

        self.connection.request(
            "GET",
            "/api/hypotheses/reversal?market=btc&days=30",
            headers=headers,
        )
        btc_response = self.connection.getresponse()
        btc_payload = json.loads(btc_response.read())
        self.assertEqual(btc_response.status, 200)
        self.assertEqual(btc_payload["market"], "btc")

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
