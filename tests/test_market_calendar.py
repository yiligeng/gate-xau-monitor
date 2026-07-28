import unittest
from datetime import datetime

from xau_monitor.market_calendar import SHANGHAI, market_calendar_payload


class MarketCalendarTests(unittest.TestCase):
    def test_includes_fomc_overnight_for_beijing_day(self) -> None:
        payload = market_calendar_payload(
            datetime(2026, 7, 29, 12, 0, tzinfo=SHANGHAI)
        )

        events = {event["title"]: event for event in payload["events"]}
        event_windows = {
            event_window["title"]: event_window
            for event_window in payload["event_windows"]
        }
        windows = {window["title"]: window for window in payload["windows"]}
        volatility_windows = {
            window["title"]: window
            for window in payload["volatility_windows"]
        }

        self.assertIn("FOMC 利率声明", events)
        self.assertIn("FOMC 发布会", events)
        self.assertIn("FOMC 夜盘", event_windows)
        self.assertNotIn("FOMC 夜盘", windows)
        self.assertEqual(events["FOMC 利率声明"]["time_label"], "07/30 02:00")
        self.assertEqual(events["FOMC 发布会"]["time_label"], "07/30 02:30")
        self.assertEqual(event_windows["FOMC 夜盘"]["time_label"], "01:50-03:30")
        self.assertIn("最高影响事件", payload["summary"])

    def test_daily_windows_and_nfp_use_beijing_time(self) -> None:
        payload = market_calendar_payload(
            datetime(2026, 8, 7, 19, 0, tzinfo=SHANGHAI)
        )

        windows = {window["title"]: window for window in payload["windows"]}
        volatility_windows = {
            window["title"]: window
            for window in payload["volatility_windows"]
        }
        event_titles = {event["title"] for event in payload["events"]}

        self.assertEqual(set(windows), {"英国午饭震荡窗", "美国午饭震荡窗"})
        self.assertEqual(windows["英国午饭震荡窗"]["time_label"], "19:00-20:30")
        self.assertEqual(windows["美国午饭震荡窗"]["time_label"], "00:00-01:30")
        self.assertEqual(windows["美国午饭震荡窗"]["impact"], "震荡")
        self.assertEqual(volatility_windows["美国数据窗"]["time_label"], "20:25-20:45")
        self.assertEqual(volatility_windows["纽约主波动"]["time_label"], "21:30-23:30")
        self.assertIn("ice.com", volatility_windows["LBMA 上午定盘"]["source_url"])
        self.assertIn("非农就业 NFP", event_titles)


if __name__ == "__main__":
    unittest.main()
