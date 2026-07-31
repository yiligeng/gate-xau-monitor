import unittest
from datetime import datetime, timedelta, timezone

from xau_monitor.reversal_hypothesis import build_hypothesis_dashboard


class ReversalHypothesisTests(unittest.TestCase):
    def test_classifies_selected_minute_persistent_reversal(self) -> None:
        start = datetime(2026, 7, 31, 2, 0, tzinfo=timezone.utc)
        candles = []
        for index in range(70):
            opened_at = start + timedelta(minutes=index)
            open_price = 100.0
            close_price = 100.1
            high = 100.5
            low = 99.5
            if index == 29:
                open_price = 100.0
                close_price = 102.0
                high = 102.0
                low = 100.0
            elif 30 <= index <= 44:
                open_price = 102.0 - (index - 30) * 0.13
                close_price = 102.0 - (index - 29) * 0.13
                high = max(open_price, close_price) + 0.2
                low = min(open_price, close_price) - 0.2
            candles.append(
                {
                    "opened_at": opened_at,
                    "open": open_price,
                    "high": high,
                    "low": low,
                    "close": close_price,
                }
            )

        result = build_hypothesis_dashboard(
            candles,
            start=start,
            now=start + timedelta(minutes=70),
        )

        selected = result["summary"]["selected"]
        self.assertEqual(selected["sample_count"], 1)
        self.assertEqual(selected["reversal_5"], 1)
        self.assertEqual(selected["reversal_15"], 1)
        self.assertEqual(selected["persistent"], 1)
        self.assertEqual(result["recent"][0]["minute"], 30)
        self.assertEqual(result["recent"][0]["trade_direction"], "short")
        self.assertEqual(result["recent"][0]["classification"], "persistent")

    def test_weak_signal_is_candidate_but_not_valid_sample(self) -> None:
        start = datetime(2026, 7, 31, 2, 0, tzinfo=timezone.utc)
        candles = [
            {
                "opened_at": start + timedelta(minutes=index),
                "open": 100.0,
                "high": 100.5,
                "low": 99.5,
                "close": 100.05,
            }
            for index in range(70)
        ]

        result = build_hypothesis_dashboard(
            candles,
            start=start,
            now=start + timedelta(minutes=70),
        )

        selected = result["summary"]["selected"]
        self.assertGreater(selected["candidate_count"], 0)
        self.assertEqual(selected["sample_count"], 0)
        self.assertEqual(result["evidence"]["code"], "collecting")

    def test_does_not_bridge_market_data_gaps_for_atr(self) -> None:
        start = datetime(2026, 7, 31, 1, 0, tzinfo=timezone.utc)
        candles = [
            {
                "opened_at": start + timedelta(minutes=index),
                "open": 100.0,
                "high": 101.0,
                "low": 99.0,
                "close": 100.8,
            }
            for index in range(50)
            if index != 20
        ]

        result = build_hypothesis_dashboard(
            candles,
            start=start,
            now=start + timedelta(hours=1),
        )
        minute_30 = next(
            row for row in result["anchors"] if row["minute"] == 30
        )

        self.assertEqual(minute_30["candidate_count"], 0)

    def test_flat_signal_is_not_qualified(self) -> None:
        start = datetime(2026, 7, 31, 2, 0, tzinfo=timezone.utc)
        candles = [
            {
                "opened_at": start + timedelta(minutes=index),
                "open": 100.0,
                "high": 100.5,
                "low": 99.5,
                "close": 100.0,
            }
            for index in range(50)
        ]

        result = build_hypothesis_dashboard(
            candles,
            start=start,
            now=start + timedelta(hours=1),
        )
        minute_30 = next(
            row for row in result["anchors"] if row["minute"] == 30
        )

        self.assertEqual(minute_30["sample_count"], 0)


if __name__ == "__main__":
    unittest.main()
