import unittest
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from xau_monitor.reversal_hypothesis import (
    ReversalHypothesisStore,
    build_hypothesis_dashboard,
)


class FakeCursor:
    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def executemany(self, sql, rows):
        self.sql = sql
        self.rows = rows


class FakeConnection:
    def __init__(self):
        self.fake_cursor = FakeCursor()

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def cursor(self):
        return self.fake_cursor


class ReversalHypothesisTests(unittest.TestCase):
    def test_upserts_only_completed_candles_through_cursor(self) -> None:
        now = datetime(2026, 7, 31, 4, 30, 30, tzinfo=timezone.utc)
        candles = [
            SimpleNamespace(
                timestamp=int(now.timestamp()) - 90,
                open=1,
                high=2,
                low=1,
                close=2,
            ),
            SimpleNamespace(
                timestamp=int(now.timestamp()) - 30,
                open=2,
                high=3,
                low=2,
                close=3,
            ),
        ]
        store = ReversalHypothesisStore("postgresql://unused")
        connection = FakeConnection()
        store._connect = lambda: connection

        saved = store.upsert_completed_candles("xau", candles, now=now)

        self.assertEqual(saved, 1)
        self.assertIn(
            "INSERT INTO app.market_candles_1m",
            connection.fake_cursor.sql,
        )
        self.assertEqual(len(connection.fake_cursor.rows), 1)

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
        self.assertEqual(selected["reversal_1"], 0)
        self.assertEqual(selected["reversal_rate_1"], 0.0)
        self.assertEqual(selected["reversal_5"], 1)
        self.assertEqual(selected["reversal_15"], 1)
        self.assertEqual(selected["persistent"], 1)
        self.assertEqual(result["recent"][0]["minute"], 30)
        self.assertEqual(result["recent"][0]["trade_direction"], "short")
        self.assertEqual(result["recent"][0]["classification"], "persistent")
        minute_30 = next(row for row in result["anchors"] if row["minute"] == 30)
        self.assertAlmostEqual(minute_30["average_return_1"], 0.13)
        self.assertAlmostEqual(minute_30["average_return_5"], 0.65)
        self.assertAlmostEqual(minute_30["average_return_15"], 1.95)
        self.assertEqual(result["recent"][0]["signal_open_price"], 100.0)
        self.assertEqual(result["recent"][0]["signal_close_price"], 102.0)
        self.assertEqual(result["recent"][0]["entry_price"], 102.0)
        self.assertAlmostEqual(result["recent"][0]["price_1"], 101.87)
        self.assertAlmostEqual(result["recent"][0]["price_5"], 101.35)
        self.assertAlmostEqual(result["recent"][0]["price_15"], 100.05)
        self.assertAlmostEqual(result["recent"][0]["high_5"], 102.2)
        self.assertAlmostEqual(result["recent"][0]["low_5"], 101.15)
        self.assertAlmostEqual(result["recent"][0]["high_15"], 102.2)
        self.assertAlmostEqual(result["recent"][0]["low_15"], 99.85)
        self.assertAlmostEqual(result["recent"][0]["pre_5_open_price"], 100.0)
        self.assertAlmostEqual(result["recent"][0]["pre_5_high"], 102.0)
        self.assertAlmostEqual(result["recent"][0]["pre_5_low"], 99.5)
        self.assertAlmostEqual(result["recent"][0]["return_1"], 0.13)
        self.assertFalse(result["recent"][0]["reversal_1"])
        self.assertAlmostEqual(result["recent"][0]["return_5"], 0.65)
        self.assertAlmostEqual(result["recent"][0]["return_15"], 1.95)
        chart = result["recent"][0]["chart_candles"]
        self.assertEqual(len(chart), 20)
        self.assertEqual(chart[0]["relative_minute"], -5)
        self.assertEqual(chart[-1]["relative_minute"], 14)
        self.assertNotIn("minute_stats", result)

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
