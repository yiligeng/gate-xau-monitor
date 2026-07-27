import unittest
from unittest.mock import patch

from xau_monitor.api import GateFuturesClient


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


if __name__ == "__main__":
    unittest.main()
