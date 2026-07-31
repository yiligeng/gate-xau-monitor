from __future__ import annotations

import math
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any, Iterable
from zoneinfo import ZoneInfo

import psycopg


SHANGHAI = ZoneInfo("Asia/Shanghai")
STRATEGY_VERSION = "HYP-REV-1M-V1"
ANCHOR_MINUTES = frozenset({0, 6, 24, 30, 36, 54})
GRID_CONTROL_MINUTES = frozenset({12, 18, 42, 48})
SUPPORTED_DAY_WINDOWS = frozenset({7, 30, 90})
SIGNAL_ATR_RATIO = 0.25
SIGNAL_BODY_RATIO = 0.60
REVERSAL_ATR_RATIO = 0.30
ATR_PERIOD = 14


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class ReversalHypothesisStore:
    def __init__(self, database_url: str) -> None:
        if not database_url:
            raise RuntimeError("DATABASE_URL is required for reversal research")
        self.database_url = database_url

    def _connect(self) -> psycopg.Connection[Any]:
        return psycopg.connect(
            self.database_url,
            connect_timeout=3,
            application_name="xau-monitor-reversal-hypothesis",
        )

    def upsert_completed_candles(
        self,
        market: str,
        candles: Iterable[Any],
        now: datetime | None = None,
    ) -> int:
        if market not in {"xau", "btc"}:
            raise ValueError("invalid market")
        now = now or utc_now()
        cutoff = int(now.timestamp()) - 60
        source = "gate_tradfi" if market == "xau" else "gate_futures"
        rows = []
        for candle in candles:
            timestamp = int(candle.timestamp)
            if timestamp > cutoff:
                continue
            rows.append(
                (
                    market,
                    datetime.fromtimestamp(timestamp, timezone.utc),
                    float(candle.open),
                    float(candle.high),
                    float(candle.low),
                    float(candle.close),
                    source,
                    now,
                )
            )
        if not rows:
            return 0
        with self._connect() as connection:
            with connection.cursor() as cursor:
                cursor.executemany(
                    """
                    INSERT INTO app.market_candles_1m (
                        market, opened_at, open, high, low, close,
                        source, updated_at
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT (market, opened_at) DO UPDATE
                    SET open = EXCLUDED.open,
                        high = EXCLUDED.high,
                        low = EXCLUDED.low,
                        close = EXCLUDED.close,
                        source = EXCLUDED.source,
                        updated_at = EXCLUDED.updated_at
                    """,
                    rows,
                )
        return len(rows)

    def dashboard(
        self,
        market: str = "xau",
        days: int = 30,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        if market not in {"xau", "btc"}:
            raise ValueError("invalid market")
        if days not in SUPPORTED_DAY_WINDOWS:
            raise ValueError("invalid day window")
        now = now or utc_now()
        start = now - timedelta(days=days)
        query_start = start - timedelta(hours=1)
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT opened_at, open, high, low, close
                FROM app.market_candles_1m
                WHERE market = %s
                  AND opened_at >= %s
                  AND opened_at < %s
                ORDER BY opened_at
                """,
                (market, query_start, now),
            ).fetchall()
            coverage = connection.execute(
                """
                SELECT count(*), min(opened_at), max(opened_at)
                FROM app.market_candles_1m
                WHERE market = %s
                """,
                (market,),
            ).fetchone()
        candles = [
            {
                "opened_at": row[0],
                "open": float(row[1]),
                "high": float(row[2]),
                "low": float(row[3]),
                "close": float(row[4]),
            }
            for row in rows
        ]
        result = build_hypothesis_dashboard(candles, start=start, now=now)
        result["market"] = market
        result["days"] = days
        result["coverage"] = {
            "total_candles": int(coverage[0] or 0) if coverage else 0,
            "first_opened_at": coverage[1] if coverage else None,
            "last_opened_at": coverage[2] if coverage else None,
        }
        return result


def build_hypothesis_dashboard(
    candles: list[dict[str, Any]],
    start: datetime | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    now = now or utc_now()
    ordered = sorted(candles, key=lambda row: row["opened_at"])
    by_time = {row["opened_at"]: row for row in ordered}
    true_ranges = _true_ranges(ordered)
    events = []
    for index, signal in enumerate(ordered):
        if index < ATR_PERIOD:
            continue
        atr_window = ordered[index - ATR_PERIOD + 1 : index + 1]
        if not _is_continuous(atr_window):
            continue
        event_at = signal["opened_at"] + timedelta(minutes=1)
        if start is not None and event_at < start:
            continue
        if event_at > now - timedelta(minutes=15):
            continue
        future_5 = by_time.get(signal["opened_at"] + timedelta(minutes=5))
        future_15 = by_time.get(signal["opened_at"] + timedelta(minutes=15))
        if future_5 is None or future_15 is None:
            continue
        path_5 = _continuous_path(by_time, signal["opened_at"], 5)
        path_15 = _continuous_path(by_time, signal["opened_at"], 15)
        if path_5 is None or path_15 is None:
            continue
        atr = sum(true_ranges[index - ATR_PERIOD + 1 : index + 1]) / ATR_PERIOD
        price_range = float(signal["high"]) - float(signal["low"])
        body = float(signal["close"]) - float(signal["open"])
        body_abs = abs(body)
        body_ratio = body_abs / price_range if price_range > 0 else 0.0
        qualified = (
            atr > 0
            and body_abs >= SIGNAL_ATR_RATIO * atr
            and body_ratio >= SIGNAL_BODY_RATIO
        )
        signal_direction = 1 if body > 0 else -1 if body < 0 else 0
        entry = float(signal["close"])
        counter_return_5 = -signal_direction * (float(future_5["close"]) - entry)
        counter_return_15 = -signal_direction * (float(future_15["close"]) - entry)
        threshold = REVERSAL_ATR_RATIO * atr
        reversal_5 = qualified and signal_direction != 0 and counter_return_5 >= threshold
        reversal_15 = qualified and signal_direction != 0 and counter_return_15 >= threshold
        minute = event_at.astimezone(SHANGHAI).minute
        events.append(
            {
                "event_at": event_at,
                "minute": minute,
                "group": _minute_group(minute),
                "signal_direction": (
                    "up" if signal_direction > 0 else "down" if signal_direction < 0 else "flat"
                ),
                "trade_direction": (
                    "short" if signal_direction > 0 else "long" if signal_direction < 0 else None
                ),
                "signal_open_price": float(signal["open"]),
                "signal_close_price": float(signal["close"]),
                "entry_price": entry,
                "price_5": float(future_5["close"]),
                "price_15": float(future_15["close"]),
                "high_5": max(float(candle["high"]) for candle in path_5),
                "low_5": min(float(candle["low"]) for candle in path_5),
                "high_15": max(float(candle["high"]) for candle in path_15),
                "low_15": min(float(candle["low"]) for candle in path_15),
                "signal_body": body_abs,
                "signal_body_atr": body_abs / atr if atr else 0.0,
                "signal_body_ratio": body_ratio,
                "atr": atr,
                "qualified": qualified,
                "return_5": counter_return_5,
                "return_15": counter_return_15,
                "return_5_atr": counter_return_5 / atr if atr else 0.0,
                "return_15_atr": counter_return_15 / atr if atr else 0.0,
                "reversal_5": reversal_5,
                "reversal_15": reversal_15,
                "classification": _classification(reversal_5, reversal_15),
                "mfe_5": _countertrend_mfe(path_5, entry, signal_direction),
                "mae_5": _countertrend_mae(path_5, entry, signal_direction),
                "mfe_15": _countertrend_mfe(path_15, entry, signal_direction),
                "mae_15": _countertrend_mae(path_15, entry, signal_direction),
            }
        )

    selected = [event for event in events if event["group"] == "selected"]
    grid_control = [event for event in events if event["group"] == "grid_control"]
    other_control = [event for event in events if event["group"] == "other"]
    selected_summary = _summarize(selected)
    grid_summary = _summarize(grid_control)
    other_summary = _summarize(other_control)
    minute_groups: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for event in events:
        minute_groups[int(event["minute"])].append(event)
    anchors = [
        {"minute": minute}
        | _summarize(minute_groups.get(minute, []))
        for minute in sorted(ANCHOR_MINUTES)
    ]
    recent = [
        _serialize_event(event)
        for event in reversed(selected)
        if event["qualified"]
    ][:40]
    status = _evidence_status(selected_summary, grid_summary)
    return {
        "strategy_version": STRATEGY_VERSION,
        "generated_at": now,
        "timezone": "Asia/Shanghai",
        "parameters": {
            "anchor_minutes": sorted(ANCHOR_MINUTES),
            "grid_control_minutes": sorted(GRID_CONTROL_MINUTES),
            "signal_minutes": 1,
            "outcome_minutes": [5, 15],
            "atr_period": ATR_PERIOD,
            "signal_atr_ratio": SIGNAL_ATR_RATIO,
            "signal_body_ratio": SIGNAL_BODY_RATIO,
            "reversal_atr_ratio": REVERSAL_ATR_RATIO,
        },
        "evidence": status,
        "summary": {
            "selected": selected_summary,
            "grid_control": grid_summary,
            "other_control": other_summary,
            "lift_5": _rate_lift(selected_summary, grid_summary, "reversal_rate_5"),
            "lift_15": _rate_lift(selected_summary, grid_summary, "reversal_rate_15"),
        },
        "anchors": anchors,
        "recent": recent,
    }


def _true_ranges(candles: list[dict[str, Any]]) -> list[float]:
    ranges = []
    previous_close: float | None = None
    for candle in candles:
        high = float(candle["high"])
        low = float(candle["low"])
        if previous_close is None:
            value = high - low
        else:
            value = max(high - low, abs(high - previous_close), abs(low - previous_close))
        ranges.append(value)
        previous_close = float(candle["close"])
    return ranges


def _continuous_path(
    by_time: dict[datetime, dict[str, Any]],
    signal_opened_at: datetime,
    minutes: int,
) -> list[dict[str, Any]] | None:
    path = []
    for offset in range(1, minutes + 1):
        candle = by_time.get(signal_opened_at + timedelta(minutes=offset))
        if candle is None:
            return None
        path.append(candle)
    return path


def _is_continuous(candles: list[dict[str, Any]]) -> bool:
    return all(
        current["opened_at"] - previous["opened_at"] == timedelta(minutes=1)
        for previous, current in zip(candles, candles[1:])
    )


def _minute_group(minute: int) -> str:
    if minute in ANCHOR_MINUTES:
        return "selected"
    if minute in GRID_CONTROL_MINUTES:
        return "grid_control"
    return "other"


def _classification(reversal_5: bool, reversal_15: bool) -> str:
    if reversal_5 and reversal_15:
        return "persistent"
    if reversal_5:
        return "faded"
    if reversal_15:
        return "delayed"
    return "no_reversal"


def _countertrend_mfe(
    path: list[dict[str, Any]],
    entry: float,
    signal_direction: int,
) -> float:
    if signal_direction > 0:
        return max(entry - float(candle["low"]) for candle in path)
    return max(float(candle["high"]) - entry for candle in path)


def _countertrend_mae(
    path: list[dict[str, Any]],
    entry: float,
    signal_direction: int,
) -> float:
    if signal_direction > 0:
        return max(float(candle["high"]) - entry for candle in path)
    return max(entry - float(candle["low"]) for candle in path)


def _summarize(events: list[dict[str, Any]]) -> dict[str, Any]:
    qualified = [event for event in events if event["qualified"]]
    sample_count = len(qualified)
    reversal_5 = sum(bool(event["reversal_5"]) for event in qualified)
    reversal_15 = sum(bool(event["reversal_15"]) for event in qualified)
    persistent = sum(event["classification"] == "persistent" for event in qualified)
    delayed = sum(event["classification"] == "delayed" for event in qualified)
    faded = sum(event["classification"] == "faded" for event in qualified)
    no_reversal = sum(event["classification"] == "no_reversal" for event in qualified)
    return {
        "candidate_count": len(events),
        "sample_count": sample_count,
        "reversal_5": reversal_5,
        "reversal_15": reversal_15,
        "reversal_rate_5": _percent(reversal_5, sample_count),
        "reversal_rate_15": _percent(reversal_15, sample_count),
        "persistent": persistent,
        "persistent_rate": _percent(persistent, sample_count),
        "delayed": delayed,
        "faded": faded,
        "no_reversal": no_reversal,
        "average_return_5_atr": _average(qualified, "return_5_atr"),
        "average_return_15_atr": _average(qualified, "return_15_atr"),
        "confidence_5": _wilson_interval(reversal_5, sample_count),
        "confidence_15": _wilson_interval(reversal_15, sample_count),
    }


def _percent(numerator: int, denominator: int) -> float | None:
    return round(numerator / denominator * 100, 2) if denominator else None


def _average(events: list[dict[str, Any]], key: str) -> float | None:
    if not events:
        return None
    return round(sum(float(event[key]) for event in events) / len(events), 4)


def _wilson_interval(successes: int, total: int) -> dict[str, float] | None:
    if total <= 0:
        return None
    z = 1.959963984540054
    proportion = successes / total
    denominator = 1 + z * z / total
    centre = (proportion + z * z / (2 * total)) / denominator
    margin = (
        z
        * math.sqrt(
            proportion * (1 - proportion) / total
            + z * z / (4 * total * total)
        )
        / denominator
    )
    return {
        "low": round(max(0.0, centre - margin) * 100, 2),
        "high": round(min(1.0, centre + margin) * 100, 2),
    }


def _rate_lift(
    selected: dict[str, Any],
    control: dict[str, Any],
    key: str,
) -> float | None:
    selected_rate = selected.get(key)
    control_rate = control.get(key)
    if selected_rate is None or control_rate is None:
        return None
    return round(float(selected_rate) - float(control_rate), 2)


def _evidence_status(
    selected: dict[str, Any],
    control: dict[str, Any],
) -> dict[str, str]:
    samples = int(selected["sample_count"])
    if samples < 30:
        return {"code": "collecting", "label": "采集中"}
    lift_5 = _rate_lift(selected, control, "reversal_rate_5") or 0.0
    lift_15 = _rate_lift(selected, control, "reversal_rate_15") or 0.0
    if samples >= 100 and lift_5 > 0 and lift_15 > 0:
        selected_5 = selected.get("confidence_5")
        control_5 = control.get("confidence_5")
        if selected_5 and control_5 and selected_5["low"] > control_5["high"]:
            return {"code": "supported", "label": "初步成立"}
    if lift_5 > 0 and lift_15 > 0:
        return {"code": "promising", "label": "有迹象"}
    return {"code": "not_supported", "label": "暂未证实"}


def _serialize_event(event: dict[str, Any]) -> dict[str, Any]:
    return {
        key: value
        for key, value in event.items()
        if key not in {"qualified", "group"}
    }
