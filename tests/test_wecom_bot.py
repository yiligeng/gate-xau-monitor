import unittest

from xau_monitor.price_alerts import (
    build_point_strategy_plan,
    is_breached,
    parse_today_levels_command,
    should_alert,
    strategy_status_for_price,
)
from xau_monitor.wecom_bot import (
    extract_chat_id,
    format_market_reply,
    format_strategy_stats,
    help_message,
    select_market_id,
)


class WeComBotFormatterTests(unittest.TestCase):
    def test_selects_market_from_text(self) -> None:
        self.assertEqual(select_market_id("看一下BTC"), "btc")
        self.assertEqual(select_market_id("黄金现在怎样"), "xau")

    def test_help_mentions_read_only_boundary(self) -> None:
        self.assertIn("只读行情", help_message())
        self.assertIn("今日点位", help_message())

    def test_formats_market_reply(self) -> None:
        reply = format_market_reply(
            {
                "ok": True,
                "market": {"display_name": "XAUUSD 黄金 CFD"},
                "updated_at": 1_780_000_000,
                "ticker": {
                    "last": 4000.12,
                    "bid": 4000.0,
                    "ask": 4000.2,
                    "spread": 0.2,
                    "low": 3990.0,
                    "high": 4010.0,
                    "change_percent": 0.5,
                },
                "overall": {"bias": "偏多", "score": 9},
                "strategy": {
                    "label": "等待入场条件",
                    "direction": "long",
                    "score": 55,
                    "threshold": 80,
                    "message": "等待支撑区触发",
                    "entry": None,
                },
                "plan": ["观察 3995.00-4005.00 区间突破"],
                "feed": {"source_age_ms": 120},
                "live_volume": None,
            }
        )

        self.assertIn("XAUUSD 黄金 CFD", reply)
        self.assertIn("最新：4,000.12", reply)
        self.assertIn("只读监控", reply)

    def test_extracts_chat_id_from_common_locations(self) -> None:
        self.assertEqual(extract_chat_id({"body": {"chatid": "group1"}}), "group1")
        self.assertEqual(
            extract_chat_id({"body": {"chat_info": {"chat_id": "group2"}}}),
            "group2",
        )

    def test_parses_today_level_command(self) -> None:
        parsed = parse_today_levels_command("黄金 今日点位 4,093.67 4087.70 4087.70")

        self.assertIsNotNone(parsed)
        assert parsed is not None
        self.assertEqual(parsed.levels, [4093.67, 4087.7])

    def test_alerts_near_level_then_breaches_after_crossing(self) -> None:
        alert = {
            "level": 3997.0,
            "side": "below",
            "approach_distance": 3.0,
            "alerts_sent": 0,
            "alert_limit": 2,
            "last_alert_at": None,
        }

        self.assertTrue(should_alert(alert, 4000.0, __import__("datetime").datetime.now()))
        self.assertFalse(is_breached(alert, 4000.0))
        self.assertTrue(is_breached(alert, 3997.0))

    def test_builds_fixed_five_point_long_plan(self) -> None:
        plan = build_point_strategy_plan(4050.0, 4046.98)

        self.assertIsNotNone(plan)
        assert plan is not None
        self.assertEqual(plan["direction"], "long")
        self.assertEqual(plan["entry_price"], 4046.98)
        self.assertEqual(plan["stop_loss"], 4041.98)
        self.assertEqual(plan["take_profit"], 4051.98)

    def test_builds_fixed_five_point_short_plan(self) -> None:
        plan = build_point_strategy_plan(4050.0, 4056.25)

        self.assertIsNotNone(plan)
        assert plan is not None
        self.assertEqual(plan["direction"], "short")
        self.assertEqual(plan["entry_price"], 4056.25)
        self.assertEqual(plan["stop_loss"], 4061.25)
        self.assertEqual(plan["take_profit"], 4051.25)

    def test_tracks_long_trial_from_entry_to_win_or_loss(self) -> None:
        pending = {
            "status": "pending",
            "direction": "long",
            "entry_price": 4046.98,
            "stop_loss": 4041.98,
            "take_profit": 4051.98,
        }
        self.assertEqual(strategy_status_for_price(pending, 4047.0), "pending")
        self.assertEqual(strategy_status_for_price(pending, 4046.98), "open")
        self.assertEqual(strategy_status_for_price(pending, 4041.0), "loss")

        opened = pending | {"status": "open"}
        self.assertEqual(strategy_status_for_price(opened, 4051.98), "win")
        self.assertEqual(strategy_status_for_price(opened, 4041.98), "loss")

    def test_tracks_short_trial_from_entry_to_win_or_loss(self) -> None:
        pending = {
            "status": "pending",
            "direction": "short",
            "entry_price": 4056.25,
            "stop_loss": 4061.25,
            "take_profit": 4051.25,
        }
        self.assertEqual(strategy_status_for_price(pending, 4056.0), "pending")
        self.assertEqual(strategy_status_for_price(pending, 4056.25), "open")
        self.assertEqual(strategy_status_for_price(pending, 4062.0), "loss")

        opened = pending | {"status": "open"}
        self.assertEqual(strategy_status_for_price(opened, 4051.25), "win")
        self.assertEqual(strategy_status_for_price(opened, 4061.25), "loss")

    def test_formats_empty_strategy_stats_without_fake_win_rate(self) -> None:
        reply = format_strategy_stats(
            "xau",
            {
                "wins": 0,
                "losses": 0,
                "settled": 0,
                "open": 0,
                "pending": 3,
                "expired": 0,
                "net_points": 0,
                "win_rate": None,
                "expectancy_points": None,
                "tracking_since": None,
            },
        )

        self.assertIn("暂无已结算样本", reply)
        self.assertIn("待触发：3", reply)
        self.assertIn("不含点差、滑点和手续费", reply)


if __name__ == "__main__":
    unittest.main()
