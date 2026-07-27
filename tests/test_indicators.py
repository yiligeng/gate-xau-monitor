import unittest

from xau_monitor.api import Candle
from xau_monitor.indicators import atr, ema, rsi


class IndicatorTests(unittest.TestCase):
    def test_ema_constant_values(self):
        self.assertEqual(ema([10.0] * 30, 5), 10.0)

    def test_rsi_rising_values(self):
        self.assertEqual(rsi([float(value) for value in range(1, 30)]), 100.0)

    def test_atr_constant_range(self):
        candles = [
            Candle(timestamp=i, open=100, high=102, low=100, close=101)
            for i in range(30)
        ]
        self.assertAlmostEqual(atr(candles), 2.0)


if __name__ == "__main__":
    unittest.main()

