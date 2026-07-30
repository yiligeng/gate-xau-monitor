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

        self.assertEqual(
            set(windows),
            {
                "亚洲午饭震荡窗",
                "英国午饭震荡窗",
                "美国午饭震荡窗",
                "COMEX 日切低流动性",
            },
        )
        self.assertEqual(windows["亚洲午饭震荡窗"]["time_label"], "10:25-13:05")
        self.assertEqual(windows["英国午饭震荡窗"]["time_label"], "19:00-20:30")
        self.assertEqual(windows["美国午饭震荡窗"]["time_label"], "00:00-01:30")
        self.assertEqual(windows["美国午饭震荡窗"]["impact"], "震荡")
        self.assertEqual(windows["COMEX 日切低流动性"]["time_label"], "04:50-06:10")
        self.assertEqual(volatility_windows["东京盘启动"]["time_label"], "07:55-08:30")
        self.assertEqual(volatility_windows["人民币中间价"]["time_label"], "09:10-09:25")
        self.assertEqual(volatility_windows["中国开盘/宏观窗"]["time_label"], "09:25-10:05")
        self.assertEqual(volatility_windows["亚洲尾盘"]["time_label"], "14:55-15:15")
        self.assertEqual(volatility_windows["美国数据窗"]["time_label"], "20:25-20:45")
        self.assertEqual(volatility_windows["美国二次数据窗"]["time_label"], "21:55-22:10")
        self.assertEqual(volatility_windows["纽约主波动"]["time_label"], "21:30-23:30")
        self.assertEqual(volatility_windows["美债拍卖结果窗"]["time_label"], "00:55-01:10")
        self.assertIn("ice.com", volatility_windows["LBMA 上午定盘"]["source_url"])
        self.assertIn("非农就业 NFP", event_titles)

    def test_weekly_energy_windows_follow_new_york_weekday(self) -> None:
        eia_payload = market_calendar_payload(
            datetime(2026, 8, 5, 19, 0, tzinfo=SHANGHAI)
        )
        eia_windows = {
            window["title"]: window
            for window in eia_payload["volatility_windows"]
        }

        api_payload = market_calendar_payload(
            datetime(2026, 8, 4, 19, 0, tzinfo=SHANGHAI)
        )
        api_windows = {
            window["title"]: window
            for window in api_payload["volatility_windows"]
        }

        self.assertEqual(eia_windows["EIA 原油库存"]["time_label"], "22:25-22:45")
        self.assertEqual(api_windows["API 原油库存"]["time_label"], "04:25-04:40")

    def test_includes_boj_windows_on_decision_day(self) -> None:
        payload = market_calendar_payload(
            datetime(2026, 7, 31, 8, 0, tzinfo=SHANGHAI)
        )

        events = {event["title"]: event for event in payload["events"]}
        event_windows = {
            event_window["title"]: event_window
            for event_window in payload["event_windows"]
        }

        self.assertEqual(events["BOJ 利率决议观察窗"]["time_label"], "07/31 10:45")
        self.assertEqual(events["BOJ 发布会"]["time_label"], "07/31 14:30")
        self.assertEqual(event_windows["BOJ 议息日"]["time_label"], "10:30-14:45")


if __name__ == "__main__":
    unittest.main()
