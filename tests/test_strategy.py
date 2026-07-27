import unittest

from xau_monitor.api import Candle, Ticker
from xau_monitor.indicators import analyze_frame
from xau_monitor.strategy import (
    calculate_position_size,
    cluster_candidates,
    evaluate_scalp_strategy,
)


def candles(count: int, start: float, step: float, seconds: int) -> list[Candle]:
    rows = []
    for index in range(count):
        close = start + step * index
        rows.append(
            Candle(
                timestamp=1_780_000_000 + index * seconds,
                open=close - step * 0.25,
                high=close + 0.24,
                low=close - 0.24,
                close=close,
            )
        )
    return rows


class ScalpStrategyTests(unittest.TestCase):
    def test_clusters_nearby_levels_with_multiple_sources(self) -> None:
        zones = cluster_candidates(
            [
                {
                    "price": 4000.05,
                    "weight": 0.8,
                    "source": "1分钟",
                    "timestamp": 1,
                },
                {
                    "price": 4000.12,
                    "weight": 1.8,
                    "source": "5分钟",
                    "timestamp": 2,
                },
                {
                    "price": 4000.08,
                    "weight": 2.8,
                    "source": "15分钟",
                    "timestamp": 3,
                },
                {
                    "price": 4004,
                    "weight": 0.8,
                    "source": "1分钟",
                    "timestamp": 4,
                },
            ],
            0.25,
        )

        self.assertEqual(len(zones), 2)
        self.assertTrue(zones[0]["quality"])
        self.assertEqual(
            set(zones[0]["sources"]),
            {"1分钟", "5分钟", "15分钟"},
        )
        self.assertGreaterEqual(zones[0]["score"], 25)

    def test_position_size_uses_fixed_account_risk(self) -> None:
        sizing = calculate_position_size(500, 0.25, 4001, 4000, 100)

        self.assertEqual(sizing["riskUsd"], 1.25)
        self.assertEqual(sizing["distance"], 1)
        self.assertEqual(sizing["lots"], 0.0125)

    def test_blocks_trade_when_timeframes_are_not_aligned(self) -> None:
        one = candles(200, 4000, 0, 60)
        five = candles(100, 4000, 0, 300)
        fifteen = candles(80, 4000, 0, 900)
        frames = {
            "1m": analyze_frame(one, "1m"),
            "5m": analyze_frame(five, "5m"),
            "15m": analyze_frame(fifteen, "15m"),
        }
        ticker = Ticker(
            timestamp_ms=(one[-1].timestamp + 30) * 1000,
            last=4000,
            bid=3999.95,
            ask=4000.05,
            high=4001,
            low=3999,
            open=4000,
            previous_close=4000,
            change_percent=0,
            status="trading",
        )

        result = evaluate_scalp_strategy(
            ticker,
            frames,
            {"1m": one, "5m": five, "15m": fifteen},
            None,
            None,
        )

        self.assertEqual(result["state"], "wait")
        self.assertEqual(result["direction"], "neutral")
        self.assertIn("禁止猜方向", result["message"])


if __name__ == "__main__":
    unittest.main()
