import unittest
from unittest.mock import patch

from xau_monitor.api import GateFuturesClient, GateTradFiClient, ticker_from_payload


class StubFuturesClient(GateFuturesClient):
    def _get(self, path, params=None):
        if path.endswith("candlesticks"):
            return [
                {
                    "t": 1_000 + index * 60,
                    "o": "50000",
                    "h": "50100",
                    "l": "49900",
                    "c": "50000",
                    "v": 10000 + index,
                    "sum": str(1000 + index * 10),
                }
                for index in range(22)
            ]
        if path.endswith("trades"):
            return [
                {
                    "create_time_ms": 2_259.5,
                    "size": 10,
                    "price": "50000",
                },
                {
                    "create_time_ms": 2_259.8,
                    "size": -5,
                    "price": "50000",
                },
            ]
        raise AssertionError(path)


class StubTradFiClient(GateTradFiClient):
    def _get_public(self, path, params=None):
        pair = params["currency_pair"]
        if path.endswith("candlesticks"):
            return [
                [
                    str(1_000 + index * 60),
                    str(1_000 + index * 10),
                    "4000",
                    "4001",
                    "3999",
                    "4000",
                    "0.25",
                    "true",
                ]
                for index in range(22)
            ]
        if path.endswith("trades") and pair == "XAUT_USDT":
            return [
                {
                    "create_time_ms": "2259.500",
                    "side": "buy",
                    "amount": "0.01",
                    "price": "4000",
                },
                {
                    "create_time_ms": "2259.800",
                    "side": "sell",
                    "amount": "0.005",
                    "price": "4000",
                },
            ]
        if path.endswith("trades"):
            return []
        raise AssertionError(path)


class FuturesVolumeTests(unittest.TestCase):
    @patch("xau_monitor.api.time.time", return_value=2260.0)
    def test_builds_real_perpetual_volume_and_trade_delta(self, _time) -> None:
        proxy = StubFuturesClient().volume_proxy("BTC_USDT")
        market = proxy["markets"][0]

        self.assertEqual(proxy["active_symbol"], "BTC_USDT")
        self.assertEqual(market["trade_count_60s"], 2)
        self.assertAlmostEqual(market["buy_quote_60s"], 50)
        self.assertAlmostEqual(market["sell_quote_60s"], 25)
        self.assertAlmostEqual(market["delta_percent"], 100 / 3)
        self.assertAlmostEqual(market["freshness_ms"], 200)


class TradFiVolumeProxyTests(unittest.TestCase):
    @patch("xau_monitor.api.time.time", return_value=2260.0)
    def test_builds_gold_spot_proxy_volume(self, _time) -> None:
        proxy = StubTradFiClient().volume_proxy("XAUUSD")
        market = proxy["markets"][0]

        self.assertEqual(proxy["active_symbol"], "XAUT_USDT")
        self.assertEqual(market["symbol"], "XAUT_USDT")
        self.assertEqual(market["trade_count_60s"], 2)
        self.assertAlmostEqual(market["buy_quote_60s"], 40)
        self.assertAlmostEqual(market["sell_quote_60s"], 20)
        self.assertAlmostEqual(market["delta_percent"], 100 / 3)
        self.assertAlmostEqual(market["freshness_ms"], 200)

    def test_ticker_keeps_official_market_session_fields(self) -> None:
        ticker = ticker_from_payload(
            {
                "timestamp": 1_000_000,
                "data": {
                    "last_price": "4050.2",
                    "bid_price": "4050.1",
                    "ask_price": "4050.3",
                    "highest_price": "4100",
                    "lowest_price": "4000",
                    "today_open_price": "4075",
                    "last_today_close_price": "4070",
                    "price_change": "-0.5",
                    "status": "closed",
                    "close_time": 1_700_000_000,
                    "open_time": 1_699_900_000,
                    "next_open_time": 1_700_200_000,
                    "trade_mode": "0",
                },
            }
        )

        self.assertEqual(ticker.status, "closed")
        self.assertEqual(ticker.next_open_time, 1_700_200_000)
        self.assertEqual(ticker.trade_mode, 0)


if __name__ == "__main__":
    unittest.main()
