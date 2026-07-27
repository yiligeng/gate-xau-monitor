from __future__ import annotations

import json
import http.client
import statistics
import time
from dataclasses import dataclass
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlsplit
from urllib.request import Request, urlopen


class GateAPIError(RuntimeError):
    """Raised when Gate returns an invalid or unsuccessful response."""


@dataclass(frozen=True)
class Ticker:
    timestamp_ms: int
    last: float
    bid: float
    ask: float
    high: float
    low: float
    open: float
    previous_close: float
    change_percent: float
    status: str

    @property
    def spread(self) -> float:
        return self.ask - self.bid


@dataclass(frozen=True)
class Candle:
    timestamp: int
    open: float
    high: float
    low: float
    close: float


class GateTradFiClient:
    def __init__(
        self,
        base_url: str = "https://api.gateio.ws/api/v4",
        timeout: float = 8.0,
        retries: int = 2,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.retries = retries

    def _get(self, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        url = f"{self.base_url}{path}"
        if params:
            url = f"{url}?{urlencode(params)}"

        request = Request(
            url,
            headers={
                "Accept": "application/json",
                "User-Agent": "gate-xau-monitor/0.1",
            },
        )
        last_error: Exception | None = None
        for attempt in range(self.retries + 1):
            try:
                with urlopen(request, timeout=self.timeout) as response:
                    payload = json.load(response)
                if not isinstance(payload, dict) or "data" not in payload:
                    raise GateAPIError(f"Gate 返回了无法识别的数据：{payload!r}")
                return payload
            except (HTTPError, URLError, TimeoutError, json.JSONDecodeError, GateAPIError) as exc:
                last_error = exc
                if attempt < self.retries:
                    time.sleep(0.4 * (2**attempt))

        raise GateAPIError(f"请求 Gate 行情失败：{last_error}") from last_error

    def ticker(self, symbol: str = "XAUUSD") -> Ticker:
        payload = self._get(f"/tradfi/symbols/{symbol}/tickers")
        return ticker_from_payload(payload)

    def candles(
        self,
        symbol: str = "XAUUSD",
        interval: str = "1m",
        limit: int = 200,
    ) -> list[Candle]:
        payload = self._get(
            f"/tradfi/symbols/{symbol}/klines",
            {"kline_type": interval, "limit": limit},
        )
        rows = payload["data"]["list"]
        candles = [
            Candle(
                timestamp=int(row["t"]),
                open=float(row["o"]),
                high=float(row["h"]),
                low=float(row["l"]),
                close=float(row["c"]),
            )
            for row in rows
        ]
        candles.sort(key=lambda item: item.timestamp)
        if len(candles) < 55:
            raise GateAPIError(f"{interval} K线数量不足：仅返回 {len(candles)} 根")
        return candles


class GateFuturesClient:
    """Read-only Gate USDT perpetual market data."""

    contract_unit = 0.0001

    def __init__(
        self,
        base_url: str = "https://api.gateio.ws/api/v4",
        timeout: float = 8.0,
        retries: int = 2,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.retries = retries

    def _get(self, path: str, params: dict[str, Any] | None = None) -> Any:
        url = f"{self.base_url}{path}"
        if params:
            url = f"{url}?{urlencode(params)}"
        request = Request(
            url,
            headers={
                "Accept": "application/json",
                "User-Agent": "gate-xau-monitor/0.1",
            },
        )
        last_error: Exception | None = None
        for attempt in range(self.retries + 1):
            try:
                with urlopen(request, timeout=self.timeout) as response:
                    return json.load(response)
            except (HTTPError, URLError, TimeoutError, json.JSONDecodeError) as exc:
                last_error = exc
                if attempt < self.retries:
                    time.sleep(0.4 * (2**attempt))
        raise GateAPIError(f"请求 Gate 永续行情失败：{last_error}") from last_error

    def ticker(self, symbol: str = "BTC_USDT") -> Ticker:
        payload = self._get(
            "/futures/usdt/tickers",
            {"contract": symbol},
        )
        if not isinstance(payload, list) or not payload:
            raise GateAPIError(f"{symbol} 永续报价缺失")
        data = payload[0]
        last = float(data["last"])
        bid = float(data["highest_bid"])
        ask = float(data["lowest_ask"])
        change_percent = float(data["change_percentage"])
        previous_close = last / (1.0 + change_percent / 100.0)
        return Ticker(
            timestamp_ms=int(time.time() * 1000),
            last=last,
            bid=bid,
            ask=ask,
            high=float(data["high_24h"]),
            low=float(data["low_24h"]),
            open=previous_close,
            previous_close=previous_close,
            change_percent=change_percent,
            status="trading",
        )

    def candles(
        self,
        symbol: str = "BTC_USDT",
        interval: str = "1m",
        limit: int = 200,
    ) -> list[Candle]:
        payload = self._get(
            "/futures/usdt/candlesticks",
            {"contract": symbol, "interval": interval, "limit": limit},
        )
        if not isinstance(payload, list):
            raise GateAPIError(f"{interval} {symbol} 永续K线数据缺失")
        candles = [
            Candle(
                timestamp=int(row["t"]),
                open=float(row["o"]),
                high=float(row["h"]),
                low=float(row["l"]),
                close=float(row["c"]),
            )
            for row in payload
        ]
        candles.sort(key=lambda item: item.timestamp)
        if len(candles) < 55:
            raise GateAPIError(
                f"{interval} {symbol} 永续K线数量不足：仅返回 {len(candles)} 根"
            )
        return candles

    def volume_proxy(self, symbol: str = "BTC_USDT") -> dict[str, Any]:
        now_seconds = int(time.time())
        raw_candles = self._get(
            "/futures/usdt/candlesticks",
            {"contract": symbol, "interval": "1m", "limit": 22},
        )
        raw_trades = self._get(
            "/futures/usdt/trades",
            {
                "contract": symbol,
                "from": now_seconds - 60,
                "to": now_seconds,
                "limit": 1000,
            },
        )
        if not isinstance(raw_candles, list) or not raw_candles:
            raise GateAPIError(f"{symbol} 永续成交量缺失")

        volume_candles: list[dict[str, float]] = []
        for row in raw_candles:
            close = float(row["c"])
            contracts = abs(float(row["v"]))
            quote = (
                contracts * self.contract_unit * close
                if row.get("sum") is None
                else float(row["sum"])
            )
            volume_candles.append(
                {
                    "timestamp": float(row["t"]),
                    "base": contracts * self.contract_unit,
                    "quote": quote,
                }
            )
        volume_candles.sort(key=lambda item: item["timestamp"])
        latest = volume_candles[-1]
        baseline_rows = [
            item["quote"] for item in volume_candles[-21:-1]
        ]
        baseline = statistics.median(baseline_rows) if baseline_rows else 0.0
        elapsed = max(
            5.0,
            min(60.0, time.time() - latest["timestamp"]),
        )
        projected = latest["quote"] * (60.0 / elapsed)

        trades: list[dict[str, float]] = []
        if isinstance(raw_trades, list):
            for row in raw_trades:
                size = float(row["size"])
                price = float(row["price"])
                trades.append(
                    {
                        "timestamp_ms": float(row["create_time_ms"]) * 1000.0,
                        "size": size,
                        "quote": abs(size) * self.contract_unit * price,
                    }
                )
        buy_quote = sum(item["quote"] for item in trades if item["size"] > 0)
        sell_quote = sum(item["quote"] for item in trades if item["size"] < 0)
        traded_quote = buy_quote + sell_quote
        newest_trade = max(
            (item["timestamp_ms"] for item in trades),
            default=0.0,
        )
        market = {
            "symbol": symbol,
            "current_base": latest["base"],
            "current_quote": latest["quote"],
            "projected_quote": projected,
            "baseline_quote": baseline,
            "rvol": projected / baseline if baseline > 0 else 0.0,
            "buy_quote_60s": buy_quote,
            "sell_quote_60s": sell_quote,
            "delta_percent": (
                (buy_quote - sell_quote) / traded_quote * 100.0
                if traded_quote > 0
                else 0.0
            ),
            "trade_count_60s": len(trades),
            "freshness_ms": (
                max(0.0, time.time() * 1000.0 - newest_trade)
                if newest_trade > 0
                else None
            ),
        }
        rvol = market["rvol"]
        status = "放量" if rvol >= 1.5 else "缩量" if 0 < rvol < 0.65 else "常态"
        return {
            "source": "Gate BTCUSDT 永续合约",
            "methodology": "BTC_USDT 永续真实合约成交量与逐笔主动方向",
            "active_symbol": symbol,
            "status": status,
            "markets": [market],
        }


def ticker_from_payload(payload: dict[str, Any]) -> Ticker:
    data = payload["data"]
    return Ticker(
        timestamp_ms=int(payload["timestamp"]),
        last=float(data["last_price"]),
        bid=float(data["bid_price"]),
        ask=float(data["ask_price"]),
        high=float(data["highest_price"]),
        low=float(data["lowest_price"]),
        open=float(data["today_open_price"]),
        previous_close=float(data["last_today_close_price"]),
        change_percent=float(data["price_change"]),
        status=str(data["status"]),
    )


class GateTradFiTickerConnection:
    """Low-latency ticker reader that reuses one HTTPS connection."""

    def __init__(
        self,
        base_url: str = "https://api.gateio.ws/api/v4",
        timeout: float = 8.0,
    ) -> None:
        parsed = urlsplit(base_url)
        if parsed.scheme != "https" or not parsed.hostname:
            raise ValueError("高频连接仅支持有效的 HTTPS Gate 地址")
        self.host = parsed.hostname
        self.port = parsed.port
        self.base_path = parsed.path.rstrip("/")
        self.timeout = timeout
        self.connection: http.client.HTTPSConnection | None = None

    def _ensure_connection(self) -> http.client.HTTPSConnection:
        if self.connection is None:
            self.connection = http.client.HTTPSConnection(
                self.host,
                port=self.port,
                timeout=self.timeout,
            )
        return self.connection

    def ticker(self, symbol: str = "XAUUSD") -> Ticker:
        connection = self._ensure_connection()
        path = f"{self.base_path}/tradfi/symbols/{symbol}/tickers"
        try:
            connection.request(
                "GET",
                path,
                headers={
                    "Accept": "application/json",
                    "User-Agent": "gate-xau-monitor/0.1",
                    "Connection": "keep-alive",
                },
            )
            response = connection.getresponse()
            raw = response.read()
            if response.status != 200:
                raise GateAPIError(
                    f"Gate 高频行情返回 HTTP {response.status}："
                    f"{raw[:160].decode('utf-8', errors='replace')}"
                )
            payload = json.loads(raw)
            if not isinstance(payload, dict) or "data" not in payload:
                raise GateAPIError(f"Gate 返回了无法识别的数据：{payload!r}")
            return ticker_from_payload(payload)
        except Exception:
            self.close()
            raise

    def close(self) -> None:
        if self.connection is not None:
            self.connection.close()
            self.connection = None
