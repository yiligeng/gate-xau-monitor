from __future__ import annotations

import json
import os
import threading
import time
import webbrowser
from collections import deque
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from .api import GateFuturesClient, GateTradFiClient, GateTradFiTickerConnection
from .auth import (
    SESSION_COOKIE,
    SESSION_TTL,
    AuthSession,
    AuthStore,
    DuplicateUsername,
    InvalidCredentials,
    InvalidInput,
)
from .indicators import analyze_frame
from .market_calendar import market_calendar_payload
from .monitor import Snapshot, fetch_snapshot, overall_bias, short_term_plan
from .price_alerts import PriceAlertStore, dedupe_levels
from .strategy import evaluate_scalp_strategy


def calculate_daily_pivots(candles: list[Any]) -> dict[str, float | int] | None:
    """Calculate classic pivots from the previous completed daily candle."""
    if len(candles) < 2:
        return None
    previous = candles[-2]
    pivot = (previous.high + previous.low + previous.close) / 3
    price_range = previous.high - previous.low
    return {
        "timestamp": previous.timestamp,
        "high": previous.high,
        "low": previous.low,
        "close": previous.close,
        "p": pivot,
        "r1": 2 * pivot - previous.low,
        "r2": pivot + price_range,
        "s1": 2 * pivot - previous.high,
        "s2": pivot - price_range,
    }


class DashboardServer(ThreadingHTTPServer):
    daemon_threads = True
    block_on_close = False


class MarketState:
    def __init__(
        self,
        client: Any,
        symbol: str,
        market: dict[str, Any],
        quote_interval: float,
        analysis_interval: float,
    ) -> None:
        self.client = client
        self.symbol = symbol
        self.market = market
        self.quote_interval = max(0.25, quote_interval)
        self.analysis_interval = max(2.0, analysis_interval)
        self.snapshot: Snapshot | None = None
        self.volume_proxy: dict[str, Any] | None = None
        self.error: str | None = None
        self.updated_at = 0.0
        self.quote_latency_ms = 0.0
        self.quote_sequence = 0
        self.tick_history: deque[dict[str, float | int]] = deque(maxlen=480)
        self.quote_event_times: deque[float] = deque(maxlen=120)
        self.price_change_times: deque[float] = deque(maxlen=120)
        self.last_recorded_price: float | None = None
        self.lock = threading.Lock()
        self.stop_event = threading.Event()

    def initialize(self) -> None:
        try:
            snapshot = fetch_snapshot(self.client, self.symbol)
            try:
                daily_candles = self.client.candles(self.symbol, "1d", 200)
                snapshot = Snapshot(
                    ticker=snapshot.ticker,
                    frames=snapshot.frames,
                    candles=snapshot.candles | {"1d": daily_candles},
                )
            except Exception:
                # Intraday monitoring should remain available if the optional
                # daily pivot request temporarily fails.
                pass
            volume_proxy = self._fetch_volume_proxy()
            with self.lock:
                self.snapshot = snapshot
                self.volume_proxy = volume_proxy
                self.error = None
                self.updated_at = time.time()
        except Exception as exc:
            with self.lock:
                self.error = str(exc)

    def run_quote_lane(self, initial_delay: float, lane_period: float) -> None:
        quote_connection: Any
        if self.market["id"] == "xau":
            quote_connection = GateTradFiTickerConnection(
                base_url=self.client.base_url,
                timeout=self.client.timeout,
            )
        else:
            quote_connection = self.client
        if self.stop_event.wait(initial_delay):
            return
        try:
            while not self.stop_event.is_set():
                with self.lock:
                    initialized = self.snapshot is not None
                if not initialized:
                    self.stop_event.wait(lane_period)
                    continue
                started = time.monotonic()
                try:
                    ticker = quote_connection.ticker(self.symbol)
                    latency_ms = (time.monotonic() - started) * 1000
                    with self.lock:
                        if (
                            self.snapshot is not None
                            and ticker.timestamp_ms >= self.snapshot.ticker.timestamp_ms
                        ):
                            self.snapshot = Snapshot(
                                ticker=ticker,
                                frames=self.snapshot.frames,
                                candles=self.snapshot.candles,
                            )
                            self.error = None
                            self.updated_at = time.time()
                            self.quote_latency_ms = latency_ms
                            self.quote_sequence += 1
                            event_time = time.monotonic()
                            self.quote_event_times.append(event_time)
                            if (
                                self.last_recorded_price is None
                                or ticker.last != self.last_recorded_price
                            ):
                                self.price_change_times.append(event_time)
                            self.last_recorded_price = ticker.last
                            self.tick_history.append(
                                {
                                    "timestamp_ms": ticker.timestamp_ms,
                                    "last": ticker.last,
                                    "bid": ticker.bid,
                                    "ask": ticker.ask,
                                }
                            )
                except Exception as exc:
                    with self.lock:
                        self.error = str(exc)
                elapsed = time.monotonic() - started
                self.stop_event.wait(max(0.01, lane_period - elapsed))
        finally:
            if self.market["id"] == "xau":
                quote_connection.close()

    def run_analysis(self) -> None:
        intervals = ("1m", "5m", "15m", "1d")
        while not self.stop_event.wait(self.analysis_interval):
            with self.lock:
                needs_initialization = self.snapshot is None
            if needs_initialization:
                self.initialize()
                continue
            try:
                with ThreadPoolExecutor(max_workers=4) as pool:
                    futures = {
                        interval: pool.submit(
                            self.client.candles,
                            self.symbol,
                            interval,
                            200,
                        )
                        for interval in intervals
                    }
                    candles = {
                        interval: future.result()
                        for interval, future in futures.items()
                    }
                frames = {
                    interval: analyze_frame(rows, interval)
                    for interval, rows in candles.items()
                    if interval != "1d"
                }
                volume_proxy = self._fetch_volume_proxy()
                with self.lock:
                    if self.snapshot is not None:
                        self.snapshot = Snapshot(
                            ticker=self.snapshot.ticker,
                            frames=frames,
                            candles=candles,
                        )
                    if volume_proxy is not None:
                        self.volume_proxy = volume_proxy
                    self.error = None
            except Exception as exc:
                with self.lock:
                    self.error = str(exc)

    def _fetch_volume_proxy(self) -> dict[str, Any] | None:
        volume_method = getattr(self.client, "volume_proxy", None)
        if volume_method is None:
            return None
        try:
            return volume_method(self.symbol)
        except Exception:
            return None

    def payload(self) -> dict[str, Any]:
        with self.lock:
            if self.snapshot is None:
                return {
                    "ok": False,
                    "symbol": self.symbol,
                    "error": self.error or "行情正在初始化",
                }
            snapshot = self.snapshot
            volume_proxy = self.volume_proxy
            bias, score = overall_bias(snapshot.frames)
            now_monotonic = time.monotonic()
            rate_window = 2.0
            quote_hz = sum(
                event >= now_monotonic - rate_window
                for event in self.quote_event_times
            ) / rate_window
            price_change_hz = sum(
                event >= now_monotonic - rate_window
                for event in self.price_change_times
            ) / rate_window
            pivots = calculate_daily_pivots(snapshot.candles.get("1d", []))
            plan = short_term_plan(snapshot)
            if volume_proxy:
                markets = volume_proxy.get("markets", [])
                active = next(
                    (
                        item
                        for item in markets
                        if item["symbol"] == volume_proxy.get("active_symbol")
                    ),
                    markets[0] if markets else None,
                )
                if active:
                    suffix = (
                        "（永续真实成交）"
                        if self.market["id"] == "btc"
                        else "（非COMEX）"
                    )
                    plan.append(
                        f"{active['symbol'].replace('_', '/')} 实时量能："
                        f"RVOL {active['rvol']:.2f}×，近60秒主动差 "
                        f"{active['delta_percent']:+.0f}%{suffix}"
                    )
            strategy = evaluate_scalp_strategy(
                snapshot.ticker,
                snapshot.frames,
                snapshot.candles,
                pivots,
                volume_proxy,
            )
            return {
                "ok": True,
                "symbol": self.symbol,
                "market": self.market,
                "updated_at": self.updated_at,
                "error": self.error,
                "feed": {
                    "mode": (
                        "Gate 永续 REST 后端轮询"
                        if self.market["id"] == "btc"
                        else "Gate TradFi REST 后端高频轮询"
                    ),
                    "quote_interval_ms": round(self.quote_interval * 1000),
                    "latency_ms": round(self.quote_latency_ms, 1),
                    "sequence": self.quote_sequence,
                    "quote_hz": round(quote_hz, 2),
                    "price_change_hz": round(price_change_hz, 2),
                    "source_age_ms": max(
                        0,
                        round(time.time() * 1000 - snapshot.ticker.timestamp_ms),
                    ),
                },
                "ticker": asdict(snapshot.ticker)
                | {"spread": snapshot.ticker.spread},
                "frames": {
                    interval: asdict(frame)
                    for interval, frame in snapshot.frames.items()
                },
                "candles": {
                    interval: [
                        asdict(candle) for candle in rows[-200:]
                    ]
                    for interval, rows in snapshot.candles.items()
                },
                "daily_pivots": pivots,
                "volume_proxy": volume_proxy,
                "live_volume": (
                    volume_proxy["markets"][0]
                    if volume_proxy and volume_proxy.get("markets")
                    else None
                ),
                "ticks": list(self.tick_history)[-240:],
                "overall": {"bias": bias, "score": score},
                "plan": plan,
                "strategy": strategy,
                "market_calendar": market_calendar_payload(),
            }

    def stop(self) -> None:
        self.stop_event.set()


def make_handler(
    states: dict[str, MarketState],
    auth_store: AuthStore,
    alert_store: PriceAlertStore | None = None,
) -> type[BaseHTTPRequestHandler]:
    static_dir = Path(__file__).with_name("web_static")
    content_types = {
        ".html": "text/html; charset=utf-8",
        ".css": "text/css; charset=utf-8",
        ".js": "text/javascript; charset=utf-8",
        ".png": "image/png",
        ".svg": "image/svg+xml",
    }

    class DashboardHandler(BaseHTTPRequestHandler):
        server_version = "WebServer"
        sys_version = ""

        def do_GET(self) -> None:
            parsed = urlparse(self.path)
            path = parsed.path
            if path == "/login":
                session = self._current_session()
                if self._auth_backend_failed:
                    self._send_error_json(503, "登录服务暂不可用")
                elif session is not None:
                    self._redirect("/")
                else:
                    self._send_static("login.html")
                return
            if path in {"/auth.css", "/auth.js", "/favicon.png"}:
                self._send_static(path.lstrip("/"))
                return

            session = self._require_session(path)
            if session is None:
                return
            if path == "/api/auth/me":
                self._send_json(
                    {
                        "ok": True,
                        "user": {
                            "id": session.user.id,
                            "username": session.user.username,
                        },
                    }
                )
                return
            market_id = parse_qs(parsed.query).get("market", ["xau"])[0]
            state = states.get(market_id, states["xau"])
            if path == "/api/bot/alerts":
                self._bot_alerts_get(state)
                return
            if path == "/api/bot/strategy-stats":
                self._bot_strategy_dashboard_get()
                return
            if path in {"/api/snapshot", "/api/quote"}:
                payload = state.payload()
                if path == "/api/quote" and payload.get("ok"):
                    payload = {
                        "ok": True,
                        "symbol": payload["symbol"],
                        "ticker": payload["ticker"],
                        "feed": payload["feed"],
                        "live_volume": payload["live_volume"],
                        "strategy": payload["strategy"],
                    }
                self._send_json(payload)
                return
            if path == "/api/stream":
                self._send_stream(state)
                return

            if path == "/":
                filename = "dashboard.html"
            elif path == "/account":
                filename = "account.html"
            else:
                filename = path.lstrip("/")
            if filename not in {
                "dashboard.html",
                "dashboard.css",
                "dashboard.js",
                "account.html",
                "account.js",
                "auth.css",
                "favicon.png",
                "apple-touch-icon.png",
            }:
                self.send_error(404)
                return

            self._send_static(filename)

        def do_POST(self) -> None:
            path = urlparse(self.path).path
            if not self._valid_origin():
                self._send_error_json(403, "请求来源无效")
                return
            if path == "/api/auth/login":
                self._login()
                return

            session = self._require_session(path)
            if session is None:
                return
            if path == "/api/auth/logout":
                auth_store.logout(session.raw_token)
                self._send_json(
                    {"ok": True},
                    headers={"Set-Cookie": self._clear_cookie()},
                )
                return
            if path == "/api/auth/change-credentials":
                self._change_credentials(session)
                return
            if path == "/api/bot/alerts":
                self._bot_alerts_replace()
                return
            if path == "/api/bot/alerts/cancel":
                self._bot_alerts_cancel()
                return
            self._send_error_json(404, "接口不存在")

        def _bot_alerts_get(self, state: MarketState) -> None:
            if alert_store is None:
                self._send_error_json(503, "机器人点位数据库未启用")
                return
            parsed = urlparse(self.path)
            query = parse_qs(parsed.query)
            market_id = query.get("market", [state.market["id"]])[0]
            chat_id = query.get("chat_id", [""])[0].strip() or None
            if market_id not in states:
                self._send_error_json(400, "未知市场")
                return
            payload = states[market_id].payload()
            if not payload.get("ok"):
                self._send_error_json(503, payload.get("error", "行情暂不可用"))
                return
            try:
                state_payload = alert_store.web_state(
                    market_id,
                    float(payload["ticker"]["last"]),
                    chat_id,
                )
            except Exception:
                self._send_error_json(503, "机器人点位读取失败")
                return
            self._send_json({"ok": True} | self._serialize_alert_state(state_payload))

        def _bot_strategy_dashboard_get(self) -> None:
            if alert_store is None:
                self._send_error_json(503, "点位策略数据库未启用")
                return
            query = parse_qs(urlparse(self.path).query)
            try:
                market_id = query.get("market", ["xau"])[0]
                chat_id = query.get("chat_id", [""])[0].strip()
                if market_id not in states:
                    raise ValueError("unknown market")
                if not chat_id or len(chat_id) > 256:
                    raise ValueError("invalid chat")
                payload = alert_store.strategy_dashboard(
                    chat_id,
                    market_id,
                    days=int(query.get("days", ["30"])[0]),
                    direction=query.get("direction", [""])[0],
                    status=query.get("status", [""])[0],
                    setup_day=query.get("setup_day", [""])[0],
                    cursor=query.get("cursor", [""])[0] or None,
                    limit=int(query.get("limit", ["20"])[0]),
                )
            except (TypeError, ValueError):
                self._send_error_json(400, "统计筛选或分页参数无效")
                return
            except Exception:
                self._send_error_json(503, "点位策略统计读取失败")
                return
            response = self._serialize_strategy_dashboard(payload)
            response["market"] = market_id
            self._send_json({"ok": True} | response)

        def _bot_alerts_replace(self) -> None:
            if alert_store is None:
                self._send_error_json(503, "机器人点位数据库未启用")
                return
            try:
                payload = self._read_json()
                market_id = str(payload.get("market", "xau"))
                chat_id = str(payload.get("chat_id", "")).strip()
                raw_levels = payload.get("levels", [])
                if market_id not in states:
                    raise ValueError("unknown market")
                if not chat_id or len(chat_id) > 256:
                    raise ValueError("invalid chat")
                if not isinstance(raw_levels, list):
                    raise ValueError("invalid levels")
                levels = dedupe_levels([float(item) for item in raw_levels])
                if not 1 <= len(levels) <= 50:
                    raise ValueError("invalid level count")
                market_payload = states[market_id].payload()
                if not market_payload.get("ok"):
                    self._send_error_json(
                        503,
                        market_payload.get("error", "行情暂不可用"),
                    )
                    return
                current_price = float(market_payload["ticker"]["last"])
                rows = alert_store.replace_today_alerts(
                    chat_id=chat_id,
                    market=market_id,
                    levels=levels,
                    current_price=current_price,
                    created_by="web",
                    source_text="web dashboard",
                )
                state_payload = alert_store.web_state(market_id, current_price, chat_id)
            except (ValueError, TypeError):
                self._send_error_json(400, "点位格式无效")
                return
            except Exception:
                self._send_error_json(503, "机器人点位保存失败")
                return
            response = self._serialize_alert_state(state_payload)
            response["saved_count"] = len(rows)
            self._send_json({"ok": True} | response)

        def _bot_alerts_cancel(self) -> None:
            if alert_store is None:
                self._send_error_json(503, "机器人点位数据库未启用")
                return
            try:
                payload = self._read_json()
                market_id = str(payload.get("market", "xau"))
                chat_id = str(payload.get("chat_id", "")).strip()
                if market_id not in states:
                    raise ValueError("unknown market")
                if not chat_id or len(chat_id) > 256:
                    raise ValueError("invalid chat")
                count = alert_store.cancel_today_alerts(chat_id, market_id)
                market_payload = states[market_id].payload()
                current_price = (
                    float(market_payload["ticker"]["last"])
                    if market_payload.get("ok")
                    else 0.0
                )
                state_payload = alert_store.web_state(market_id, current_price, chat_id)
            except ValueError:
                self._send_error_json(400, "会话无效")
                return
            except Exception:
                self._send_error_json(503, "机器人点位取消失败")
                return
            response = self._serialize_alert_state(state_payload)
            response["cancelled_count"] = count
            self._send_json({"ok": True} | response)

        def _serialize_alert_state(self, payload: dict[str, Any]) -> dict[str, Any]:
            return {
                "market": payload["market"],
                "current_price": payload["current_price"],
                "expires_at": payload["expires_at"].isoformat(),
                "selected_chat_id": payload["selected_chat_id"],
                "chats": [
                    {
                        "chat_id": chat["chat_id"],
                        "label": chat["label"],
                        "active_count": chat["active_count"],
                        "last_seen_at": (
                            chat["last_seen_at"].isoformat()
                            if chat.get("last_seen_at")
                            else None
                        ),
                    }
                    for chat in payload["chats"]
                ],
                "alerts": [
                    self._serialize_alert(alert)
                    for alert in payload["alerts"]
                ],
                "today_alerts": [
                    self._serialize_alert(alert)
                    for alert in payload.get("today_alerts", payload["alerts"])
                ],
                "strategy": self._serialize_strategy_stats(payload["strategy"]),
            }

        def _serialize_alert(self, alert: dict[str, Any]) -> dict[str, Any]:
            result = {
                "id": alert["id"],
                "level": alert["level"],
                "created_price": alert["created_price"],
                "side": alert["side"],
                "alerts_sent": alert["alerts_sent"],
                "alert_limit": alert["alert_limit"],
                "distance": alert.get("distance"),
                "status": alert.get("status", "active"),
                "strategy": alert.get("strategy"),
            }
            for key in (
                "expires_at",
                "created_at",
                "last_alert_at",
                "breached_at",
            ):
                value = alert.get(key)
                result[key] = value.isoformat() if value else None
            return result

        def _serialize_strategy_stats(
            self,
            payload: dict[str, Any],
        ) -> dict[str, Any]:
            result = dict(payload)
            for key in ("tracking_since", "last_resolved_at"):
                value = result.get(key)
                result[key] = value.isoformat() if value else None
            result["recent"] = [
                {
                    **trial,
                    "created_at": (
                        trial["created_at"].isoformat()
                        if trial.get("created_at")
                        else None
                    ),
                    "triggered_at": (
                        trial["triggered_at"].isoformat()
                        if trial.get("triggered_at")
                        else None
                    ),
                    "resolved_at": (
                        trial["resolved_at"].isoformat()
                        if trial.get("resolved_at")
                        else None
                    ),
                }
                for trial in payload.get("recent", [])
            ]
            return result

        def _serialize_strategy_dashboard(
            self,
            payload: dict[str, Any],
        ) -> dict[str, Any]:
            return {
                "generated_at": payload["generated_at"].isoformat(),
                "daily_timezone": payload["daily_timezone"],
                "daily_grain": payload["daily_grain"],
                "days": payload["days"],
                "summary": self._serialize_strategy_stats(payload["summary"]),
                "daily": [
                    {
                        **row,
                        "setup_day": row["setup_day"].isoformat(),
                    }
                    for row in payload["daily"]
                ],
                "trials": [
                    {
                        **trial,
                        "setup_day": trial["setup_day"].isoformat(),
                        "created_at": (
                            trial["created_at"].isoformat()
                            if trial.get("created_at")
                            else None
                        ),
                        "triggered_at": (
                            trial["triggered_at"].isoformat()
                            if trial.get("triggered_at")
                            else None
                        ),
                        "resolved_at": (
                            trial["resolved_at"].isoformat()
                            if trial.get("resolved_at")
                            else None
                        ),
                    }
                    for trial in payload["trials"]
                ],
                "page": payload["page"],
                "filters": {
                    **payload["filters"],
                    "setup_day": (
                        payload["filters"]["setup_day"].isoformat()
                        if payload["filters"].get("setup_day")
                        else None
                    ),
                },
            }

        def _login(self) -> None:
            try:
                payload = self._read_json()
                username = str(payload.get("username", ""))
                password = str(payload.get("password", ""))
                session = auth_store.authenticate(
                    username,
                    password,
                    self._client_ip(),
                    self.headers.get("User-Agent", ""),
                )
            except (InvalidCredentials, InvalidInput):
                print(
                    f"AUTH_FAIL ip={self._client_ip()}",
                    flush=True,
                )
                self._send_error_json(401, "用户名或密码错误")
                return
            except (json.JSONDecodeError, ValueError):
                self._send_error_json(400, "请求格式错误")
                return
            except Exception:
                print("AUTH_ERROR login_backend_unavailable", flush=True)
                self._send_error_json(503, "登录服务暂不可用")
                return
            self._send_json(
                {
                    "ok": True,
                    "user": {
                        "id": session.user.id,
                        "username": session.user.username,
                    },
                },
                headers={"Set-Cookie": self._session_cookie(session)},
            )

        def _change_credentials(self, session: AuthSession) -> None:
            try:
                payload = self._read_json()
                current_password = str(payload.get("current_password", ""))
                new_username_value = payload.get("new_username")
                new_password_value = payload.get("new_password")
                new_username = (
                    str(new_username_value).strip()
                    if new_username_value
                    else None
                )
                new_password = (
                    str(new_password_value)
                    if new_password_value
                    else None
                )
                new_session = auth_store.change_credentials(
                    session.user.id,
                    current_password,
                    new_username,
                    new_password,
                    self._client_ip(),
                    self.headers.get("User-Agent", ""),
                )
            except InvalidCredentials as exc:
                self._send_error_json(401, str(exc))
                return
            except (InvalidInput, DuplicateUsername) as exc:
                self._send_error_json(400, str(exc))
                return
            except (json.JSONDecodeError, ValueError):
                self._send_error_json(400, "请求格式错误")
                return
            except Exception:
                print("AUTH_ERROR credential_update_failed", flush=True)
                self._send_error_json(503, "账户服务暂不可用")
                return
            self._send_json(
                {
                    "ok": True,
                    "user": {
                        "id": new_session.user.id,
                        "username": new_session.user.username,
                    },
                },
                headers={"Set-Cookie": self._session_cookie(new_session)},
            )

        def _read_json(self) -> dict[str, Any]:
            try:
                content_length = int(self.headers.get("Content-Length", "0"))
            except ValueError as exc:
                raise ValueError("invalid content length") from exc
            if content_length <= 0 or content_length > 16_384:
                raise ValueError("invalid request size")
            payload = json.loads(self.rfile.read(content_length))
            if not isinstance(payload, dict):
                raise ValueError("JSON object required")
            return payload

        def _client_ip(self) -> str:
            forwarded = self.headers.get("X-Forwarded-For", "")
            if forwarded:
                return forwarded.split(",")[-1].strip()
            return str(self.client_address[0])

        def _valid_origin(self) -> bool:
            origin = self.headers.get("Origin", "").rstrip("/")
            return origin in {
                "https://sheshetrip.fun",
                "https://www.sheshetrip.fun",
                "http://127.0.0.1:8765",
                "http://localhost:8765",
            }

        def _raw_session_token(self) -> str:
            cookie_header = self.headers.get("Cookie", "")
            if not cookie_header:
                return ""
            cookie = SimpleCookie()
            try:
                cookie.load(cookie_header)
            except Exception:
                return ""
            morsel = cookie.get(SESSION_COOKIE)
            return morsel.value if morsel is not None else ""

        def _current_session(self) -> AuthSession | None:
            self._auth_backend_failed = False
            try:
                return auth_store.get_session(self._raw_session_token())
            except Exception:
                self._auth_backend_failed = True
                print("AUTH_ERROR session_backend_unavailable", flush=True)
                return None

        def _require_session(self, path: str) -> AuthSession | None:
            session = self._current_session()
            if self._auth_backend_failed:
                self._send_error_json(503, "登录服务暂不可用")
                return None
            if session is not None:
                return session
            if path.startswith("/api/"):
                self._send_error_json(401, "需要登录")
            else:
                self._redirect("/login")
            return None

        def _session_cookie(self, session: AuthSession) -> str:
            max_age = int(SESSION_TTL.total_seconds())
            return (
                f"{SESSION_COOKIE}={session.raw_token}; Path=/; "
                f"Max-Age={max_age}; Secure; HttpOnly; SameSite=Strict"
            )

        def _clear_cookie(self) -> str:
            return (
                f"{SESSION_COOKIE}=; Path=/; Max-Age=0; "
                "Secure; HttpOnly; SameSite=Strict"
            )

        def _redirect(self, location: str) -> None:
            self.send_response(303)
            self.send_header("Location", location)
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", "0")
            self.end_headers()

        def _send_static(self, filename: str) -> None:
            if filename not in {
                "dashboard.html",
                "dashboard.css",
                "dashboard.js",
                "login.html",
                "account.html",
                "account.js",
                "auth.css",
                "auth.js",
                "favicon.png",
                "apple-touch-icon.png",
            }:
                self.send_error(404)
                return
            file_path = static_dir / filename
            try:
                body = file_path.read_bytes()
            except FileNotFoundError:
                self.send_error(404)
                return
            self.send_response(200)
            self.send_header(
                "Content-Type",
                content_types.get(file_path.suffix, "application/octet-stream"),
            )
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def _send_json(
            self,
            payload: dict[str, Any],
            status: int = 200,
            headers: dict[str, str] | None = None,
        ) -> None:
            body = json.dumps(
                payload, ensure_ascii=False, separators=(",", ":")
            ).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            for key, value in (headers or {}).items():
                self.send_header(key, value)
            self.end_headers()
            self.wfile.write(body)

        def _send_error_json(self, status: int, message: str) -> None:
            self._send_json({"ok": False, "error": message}, status=status)

        def end_headers(self) -> None:
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("X-Frame-Options", "DENY")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header(
                "Permissions-Policy",
                "camera=(), microphone=(), geolocation=()",
            )
            self.send_header(
                "Content-Security-Policy",
                "default-src 'self'; script-src 'self'; style-src 'self'; "
                "img-src 'self' data:; connect-src 'self'; "
                "frame-ancestors 'none'; base-uri 'none'; form-action 'self'",
            )
            super().end_headers()

        def _send_stream(self, state: MarketState) -> None:
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream; charset=utf-8")
            self.send_header("Cache-Control", "no-cache")
            self.send_header("Connection", "keep-alive")
            self.send_header("X-Accel-Buffering", "no")
            self.end_headers()
            last_sequence = -1
            try:
                while not state.stop_event.is_set():
                    payload = state.payload()
                    sequence = payload.get("feed", {}).get("sequence", 0)
                    if sequence != last_sequence:
                        body = json.dumps(
                            payload,
                            ensure_ascii=False,
                            separators=(",", ":"),
                        )
                        self.wfile.write(f"data:{body}\n\n".encode("utf-8"))
                        self.wfile.flush()
                        last_sequence = sequence
                    state.stop_event.wait(0.05)
            except (BrokenPipeError, ConnectionResetError):
                return

        def log_message(self, format: str, *args: Any) -> None:
            return

    return DashboardHandler


def create_market_states(
    client: GateTradFiClient,
    symbol: str,
    quote_interval: float,
    analysis_interval: float,
) -> dict[str, MarketState]:
    return {
        "xau": MarketState(
            client,
            symbol,
            {
                "id": "xau",
                "symbol": symbol,
                "display_name": "XAUUSD 黄金 CFD",
                "product": "Gate TradFi CFD",
                "mark": "Au",
                "contract_unit": 100,
                "position_unit": "手",
            },
            quote_interval,
            analysis_interval,
        ),
        "btc": MarketState(
            GateFuturesClient(timeout=client.timeout),
            "BTC_USDT",
            {
                "id": "btc",
                "symbol": "BTC_USDT",
                "display_name": "BTCUSDT 永续",
                "product": "Gate 永续合约",
                "mark": "₿",
                "contract_unit": 0.0001,
                "position_unit": "张",
            },
            max(1.0, quote_interval),
            analysis_interval,
        ),
    }


def initialize_market_states(states: dict[str, MarketState]) -> None:
    with ThreadPoolExecutor(max_workers=2) as pool:
        list(pool.map(lambda item: item.initialize(), states.values()))


def start_market_workers(states: dict[str, MarketState]) -> list[threading.Thread]:
    workers: list[threading.Thread] = []
    for state in states.values():
        lane_count = (
            max(1, min(4, round(1.0 / state.quote_interval)))
            if state.market["id"] == "xau"
            else 1
        )
        lane_period = state.quote_interval * lane_count
        workers.extend(
            threading.Thread(
                target=state.run_quote_lane,
                args=(lane * state.quote_interval, lane_period),
                daemon=True,
            )
            for lane in range(lane_count)
        )
        workers.append(
            threading.Thread(target=state.run_analysis, daemon=True)
        )
    for worker in workers:
        worker.start()
    return workers


def run_web_server(
    client: GateTradFiClient,
    symbol: str,
    quote_interval: float,
    analysis_interval: float,
    host: str,
    port: int,
    open_browser: bool,
    enable_wecom_bot: bool = False,
) -> int:
    auth_store = AuthStore(os.environ.get("DATABASE_URL", ""))
    auth_store.cleanup()
    alert_store = PriceAlertStore(os.environ.get("DATABASE_URL", ""))
    states = create_market_states(client, symbol, quote_interval, analysis_interval)
    initialize_market_states(states)
    start_market_workers(states)

    if enable_wecom_bot:
        from .wecom_bot import start_wecom_bot_thread

        start_wecom_bot_thread(states)

    server = DashboardServer(
        (host, port),
        make_handler(states, auth_store, alert_store),
    )
    display_host = "127.0.0.1" if host in {"0.0.0.0", "::"} else host
    url = f"http://{display_host}:{port}"
    print(f"Gate XAUUSD / BTCUSDT 后端监控已启动：{url}")
    print(
        f"黄金报价约每 {states['xau'].quote_interval:.2f} 秒更新，"
        f"BTC报价约每 {states['btc'].quote_interval:.2f} 秒更新，"
        f"指标每 {analysis_interval:.0f} 秒更新。"
    )
    print("关闭此终端或按 Ctrl+C 可停止监控。")
    print("数据库用户登录已启用；未登录请求不会获得仪表盘或行情 API。")
    if open_browser:
        threading.Timer(0.5, lambda: webbrowser.open(url)).start()

    try:
        server.serve_forever(poll_interval=0.5)
    finally:
        for state in states.values():
            state.stop()
        server.server_close()
    return 0
