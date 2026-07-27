import unittest

from xau_monitor.api import Candle
from xau_monitor.web import calculate_daily_pivots


class DailyPivotTests(unittest.TestCase):
    def test_uses_previous_completed_daily_candle(self) -> None:
        candles = [
            Candle(timestamp=100, open=100, high=110, low=90, close=105),
            Candle(timestamp=200, open=106, high=120, low=101, close=115),
        ]

        pivots = calculate_daily_pivots(candles)

        self.assertIsNotNone(pivots)
        assert pivots is not None
        self.assertEqual(pivots["timestamp"], 100)
        self.assertAlmostEqual(pivots["p"], 305 / 3)
        self.assertAlmostEqual(pivots["r1"], 2 * (305 / 3) - 90)
        self.assertAlmostEqual(pivots["s1"], 2 * (305 / 3) - 110)
        self.assertAlmostEqual(pivots["r2"], 305 / 3 + 20)
        self.assertAlmostEqual(pivots["s2"], 305 / 3 - 20)

    def test_requires_current_and_previous_daily_candles(self) -> None:
        candle = Candle(timestamp=100, open=100, high=110, low=90, close=105)
        self.assertIsNone(calculate_daily_pivots([candle]))


if __name__ == "__main__":
    unittest.main()
