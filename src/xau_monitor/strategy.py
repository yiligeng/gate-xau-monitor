from __future__ import annotations

from math import isfinite
from typing import Any, Iterable

from .api import Candle
from .indicators import ema_series


REWARD_RISK = 1.5
TIMEOUT_MINUTES = 8
MIN_SCORE = 80
MAX_SIGNAL_AGE_SECONDS = 180


def _completed(candles: list[Candle]) -> list[Candle]:
    return candles[:-1] if len(candles) > 2 else []


def atr_series(candles: list[Candle], period: int = 14) -> list[float]:
    if not candles:
        return []
    ranges: list[float] = []
    for index, candle in enumerate(candles):
        if index == 0:
            ranges.append(candle.high - candle.low)
            continue
        previous_close = candles[index - 1].close
        ranges.append(
            max(
                candle.high - candle.low,
                abs(candle.high - previous_close),
                abs(candle.low - previous_close),
            )
        )
    output: list[float] = []
    current = ranges[0]
    for index, true_range in enumerate(ranges):
        current = (
            true_range
            if index == 0
            else (current * (period - 1) + true_range) / period
        )
        output.append(current)
    return output


def find_swings(
    candles: list[Candle],
    level_type: str,
    source: str,
    weight: float,
    lookback: int,
) -> list[dict[str, Any]]:
    recent = _completed(candles)[-lookback:]
    points: list[dict[str, Any]] = []
    for index in range(2, len(recent) - 2):
        candle = recent[index]
        neighbors = [
            recent[index - 2],
            recent[index - 1],
            recent[index + 1],
            recent[index + 2],
        ]
        if level_type == "support":
            is_swing = all(candle.low <= item.low for item in neighbors)
            price = candle.low
        else:
            is_swing = all(candle.high >= item.high for item in neighbors)
            price = candle.high
        if is_swing:
            points.append(
                {
                    "price": price,
                    "timestamp": candle.timestamp,
                    "source": source,
                    "type": level_type,
                    "weight": weight,
                }
            )
    return points


def cluster_candidates(
    candidates: Iterable[dict[str, Any]],
    tolerance: float,
) -> list[dict[str, Any]]:
    clusters: list[dict[str, Any]] = []
    for candidate in sorted(candidates, key=lambda item: item["price"]):
        previous = clusters[-1] if clusters else None
        if previous is None or abs(candidate["price"] - previous["center"]) > tolerance:
            clusters.append(
                {
                    "center": candidate["price"],
                    "weighted_total": candidate["price"] * candidate["weight"],
                    "weight": candidate["weight"],
                    "touches": 1,
                    "sources": {candidate["source"]},
                    "latest_timestamp": candidate["timestamp"],
                }
            )
            continue
        previous["weighted_total"] += candidate["price"] * candidate["weight"]
        previous["weight"] += candidate["weight"]
        previous["touches"] += 1
        previous["sources"].add(candidate["source"])
        previous["latest_timestamp"] = max(
            previous["latest_timestamp"],
            candidate["timestamp"],
        )
        previous["center"] = previous["weighted_total"] / previous["weight"]

    zones: list[dict[str, Any]] = []
    for cluster in clusters:
        half_width = max(tolerance * 0.55, 0.12)
        zones.append(
            {
                "center": cluster["center"],
                "lower": cluster["center"] - half_width,
                "upper": cluster["center"] + half_width,
                "weight": cluster["weight"],
                "touches": cluster["touches"],
                "sources": sorted(cluster["sources"]),
                "latestTimestamp": cluster["latest_timestamp"],
                "quality": (
                    cluster["weight"] >= 3.2
                    and len(cluster["sources"]) >= 2
                ),
                "score": min(25, round(10 + cluster["weight"] * 3)),
            }
        )
    return zones


def build_zones(
    candles: dict[str, list[Candle]],
    pivots: dict[str, float | int] | None,
    price: float,
    tolerance: float,
) -> dict[str, Any]:
    supports = [
        *find_swings(candles.get("1m", []), "support", "1分钟", 0.8, 100),
        *find_swings(candles.get("5m", []), "support", "5分钟", 1.8, 90),
        *find_swings(candles.get("15m", []), "support", "15分钟", 2.8, 60),
    ]
    resistances = [
        *find_swings(candles.get("1m", []), "resistance", "1分钟", 0.8, 100),
        *find_swings(candles.get("5m", []), "resistance", "5分钟", 1.8, 90),
        *find_swings(candles.get("15m", []), "resistance", "15分钟", 2.8, 60),
    ]
    if pivots:
        for key in ("s2", "s1", "p"):
            value = float(pivots[key])
            if isfinite(value) and value <= price + tolerance:
                supports.append(
                    {
                        "price": value,
                        "timestamp": pivots["timestamp"],
                        "source": f"日枢轴{key.upper()}",
                        "type": "support",
                        "weight": 2.2,
                    }
                )
        for key in ("r2", "r1", "p"):
            value = float(pivots[key])
            if isfinite(value) and value >= price - tolerance:
                resistances.append(
                    {
                        "price": value,
                        "timestamp": pivots["timestamp"],
                        "source": f"日枢轴{key.upper()}",
                        "type": "resistance",
                        "weight": 2.2,
                    }
                )

    support_zones = sorted(
        (
            zone
            for zone in cluster_candidates(supports, tolerance)
            if zone["center"] <= price + tolerance
        ),
        key=lambda zone: zone["center"],
        reverse=True,
    )
    resistance_zones = sorted(
        (
            zone
            for zone in cluster_candidates(resistances, tolerance)
            if zone["center"] >= price - tolerance
        ),
        key=lambda zone: zone["center"],
    )
    return {
        "support": support_zones[0] if support_zones else None,
        "resistance": resistance_zones[0] if resistance_zones else None,
        "supports": support_zones[:4],
        "resistances": resistance_zones[:4],
    }


def trend_context(candles: dict[str, list[Candle]]) -> dict[str, Any]:
    five = _completed(candles.get("5m", []))
    fifteen = _completed(candles.get("15m", []))
    if len(five) < 55 or len(fifteen) < 25:
        return {
            "bias": "neutral",
            "detail": "多周期K线数量不足",
            "candidate": "neutral",
            "checks": [],
            "metrics": None,
        }
    five_closes = [candle.close for candle in five]
    fifteen_closes = [candle.close for candle in fifteen]
    five20 = ema_series(five_closes, 20)
    five50 = ema_series(five_closes, 50)
    fifteen20 = ema_series(fifteen_closes, 20)
    five_close = five_closes[-1]
    fifteen_close = fifteen_closes[-1]
    five_ema20 = five20[-1]
    five_ema20_past = five20[-4]
    five_ema50 = five50[-1]
    fifteen_ema20 = fifteen20[-1]
    five_slope = five_ema20 - five_ema20_past
    atr15 = atr_series(fifteen)[-1] or 1.0
    long_guard = fifteen_ema20 - atr15 * 0.08
    short_guard = fifteen_ema20 + atr15 * 0.08
    fifteen_not_bearish = fifteen_close >= long_guard
    fifteen_not_bullish = fifteen_close <= short_guard

    long_checks = [
        {
            "key": "close_term",
            "label": "价格站在短期平均线上方",
            "pass": five_close > five_ema20,
            "detail": f"刚收盘5分钟价格 {five_close:.2f}；短期平均线 {five_ema20:.2f}",
            "why": "看“价格现在在哪里”，避免只根据过去的趋势做多。",
        },
        {
            "key": "ema_term",
            "label": "短期平均线高于长期平均线",
            "pass": five_ema20 > five_ema50,
            "detail": f"短期平均 {five_ema20:.2f}；长期平均 {five_ema50:.2f}",
            "why": "看“整体排列”，过滤只有一两根K线反弹造成的假强势。",
        },
        {
            "key": "slope_term",
            "label": "短期平均线正在抬头",
            "pass": five_slope > 0,
            "detail": (
                f"当前 {five_ema20:.2f}；15分钟前 {five_ema20_past:.2f}；"
                f"变化 {five_slope:+.2f}"
            ),
            "why": "看“趋势是否还在前进”，避免均线虽在上方却已经走平或掉头。",
        },
        {
            "key": "higher_timeframe_term",
            "label": "15分钟没有明显转空",
            "pass": fifteen_not_bearish,
            "detail": f"15分钟收盘 {fifteen_close:.2f}；防守线 {long_guard:.2f}",
            "why": "做大周期安全检查，避免5分钟想做多时15分钟已经明显走弱。",
        },
    ]
    short_checks = [
        {
            "key": "close_term",
            "label": "价格落在短期平均线下方",
            "pass": five_close < five_ema20,
            "detail": f"刚收盘5分钟价格 {five_close:.2f}；短期平均线 {five_ema20:.2f}",
            "why": "看“价格现在在哪里”，避免只根据过去的趋势做空。",
        },
        {
            "key": "ema_term",
            "label": "短期平均线低于长期平均线",
            "pass": five_ema20 < five_ema50,
            "detail": f"短期平均 {five_ema20:.2f}；长期平均 {five_ema50:.2f}",
            "why": "看“整体排列”，过滤只有一两根K线下跌造成的假弱势。",
        },
        {
            "key": "slope_term",
            "label": "短期平均线正在低头",
            "pass": five_slope < 0,
            "detail": (
                f"当前 {five_ema20:.2f}；15分钟前 {five_ema20_past:.2f}；"
                f"变化 {five_slope:+.2f}"
            ),
            "why": "看“趋势是否还在前进”，避免均线虽在下方却已经走平或抬头。",
        },
        {
            "key": "higher_timeframe_term",
            "label": "15分钟没有明显转多",
            "pass": fifteen_not_bullish,
            "detail": (
                f"15分钟收盘 {fifteen_close:.2f}；"
                f"转多警戒线 {short_guard:.2f}"
            ),
            "why": "做大周期安全检查，避免5分钟想做空时15分钟已经明显反弹。",
        },
    ]
    bullish = all(check["pass"] for check in long_checks)
    bearish = all(check["pass"] for check in short_checks)
    long_count = sum(check["pass"] for check in long_checks)
    short_count = sum(check["pass"] for check in short_checks)
    metrics = {
        "fiveClose": five_close,
        "fiveEma20": five_ema20,
        "fiveEma20Past": five_ema20_past,
        "fiveEma50": five_ema50,
        "fiveSlope": five_slope,
        "fifteenClose": fifteen_close,
        "fifteenEma20": fifteen_ema20,
        "atr15": atr15,
        "longGuard": long_guard,
        "shortGuard": short_guard,
    }
    if bullish:
        return {
            "bias": "long",
            "detail": "趋势背景偏多；四项方向条件通过，但这还不是入场信号",
            "candidate": "long",
            "checks": long_checks,
            "metrics": metrics,
        }
    if bearish:
        return {
            "bias": "short",
            "detail": "趋势背景偏空；四项方向条件通过，但这还不是入场信号",
            "candidate": "short",
            "checks": short_checks,
            "metrics": metrics,
        }
    candidate = "short" if short_count > long_count else "long"
    return {
        "bias": "neutral",
        "detail": f"方向尚未统一：做多通过{long_count}/4，做空通过{short_count}/4",
        "candidate": candidate,
        "checks": short_checks if candidate == "short" else long_checks,
        "metrics": metrics,
    }


def volume_context(
    volume_proxy: dict[str, Any] | None,
    direction: str,
) -> dict[str, Any]:
    market = None
    if volume_proxy:
        markets = volume_proxy.get("markets", [])
        market = next(
            (
                item
                for item in markets
                if item["symbol"] == volume_proxy.get("active_symbol")
            ),
            markets[0] if markets else None,
        )
    if not market:
        return {
            "score": 5,
            "usable": False,
            "aligned": False,
            "detail": "量能暂缺，仅按价格结构",
        }
    freshness = market.get("freshness_ms")
    usable = (
        freshness is not None
        and freshness <= 20_000
        and market["trade_count_60s"] >= 5
    )
    symbol = market["symbol"].replace("_", "/")
    if not usable:
        return {
            "score": 5,
            "usable": False,
            "aligned": False,
            "detail": f"{symbol}成交稀疏，量能不参与否决",
        }
    delta = market["delta_percent"]
    delta_aligned = delta >= 15 if direction == "long" else delta <= -15
    delta_opposed = delta <= -25 if direction == "long" else delta >= 25
    active = market["rvol"] >= 1.2
    if active and delta_aligned:
        return {
            "score": 10,
            "usable": True,
            "aligned": True,
            "detail": f"RVOL {market['rvol']:.2f}×，主动差 {delta:+.0f}%",
        }
    if active and delta_opposed:
        return {
            "score": 0,
            "usable": True,
            "aligned": False,
            "detail": f"放量但主动差反向 {delta:+.0f}%",
        }
    return {
        "score": 5,
        "usable": True,
        "aligned": False,
        "detail": f"RVOL {market['rvol']:.2f}×，量能中性",
    }


def sweep_trigger(
    candle: Candle | None,
    zone: dict[str, Any] | None,
    direction: str,
    atr1: float,
) -> dict[str, Any]:
    if candle is None or zone is None:
        return {"valid": False, "detail": "等待价格触及关键区域"}
    candle_range = max(candle.high - candle.low, 0.0001)
    body = abs(candle.close - candle.open)
    close_position = (candle.close - candle.low) / candle_range
    lower_wick = min(candle.open, candle.close) - candle.low
    upper_wick = candle.high - max(candle.open, candle.close)
    if direction == "long":
        touched = candle.low <= zone["upper"]
        not_collapsed = candle.low >= zone["lower"] - atr1 * 0.35
        reclaimed = candle.close >= zone["center"] and close_position >= 0.6
        rejection = lower_wick >= max(body * 0.45, atr1 * 0.06)
        valid = touched and not_collapsed and reclaimed and rejection
        detail = (
            "1分钟下扫支撑后收回"
            if valid
            else "已触及支撑，但尚未形成强回收"
            if touched
            else "等待价格下扫支撑区域"
        )
        return {"valid": valid, "detail": detail}
    touched = candle.high >= zone["lower"]
    not_collapsed = candle.high <= zone["upper"] + atr1 * 0.35
    reclaimed = candle.close <= zone["center"] and close_position <= 0.4
    rejection = upper_wick >= max(body * 0.45, atr1 * 0.06)
    valid = touched and not_collapsed and reclaimed and rejection
    detail = (
        "1分钟上扫阻力后压回"
        if valid
        else "已触及阻力，但尚未形成强压回"
        if touched
        else "等待价格上扫阻力区域"
    )
    return {"valid": valid, "detail": detail}


def _neutral_result(
    trend: dict[str, Any],
    zones: dict[str, Any],
    atr1: float,
    tolerance: float,
) -> dict[str, Any]:
    direction = trend["bias"]
    return {
        "version": "SCALP-1.0-PY",
        "state": "wait",
        "direction": direction,
        "label": "方向未定" if direction == "neutral" else "等待入场条件",
        "score": 0 if direction == "neutral" else 25,
        "threshold": MIN_SCORE,
        "entry": None,
        "stop": None,
        "target": None,
        "risk": None,
        "rewardRisk": REWARD_RISK,
        "timeoutMinutes": TIMEOUT_MINUTES,
        "triggerTimestamp": None,
        "signature": None,
        "atr1": atr1,
        "tolerance": tolerance,
        "trend": trend,
        "zones": zones,
        "volume": {
            "score": 5,
            "usable": False,
            "aligned": False,
            "detail": "仅作辅助加分",
        },
        "checklist": [
            {
                "key": "trend",
                "label": "多周期趋势",
                "pass": direction != "neutral",
                "detail": trend["detail"],
            },
            {
                "key": "zone",
                "label": "关键位区域",
                "pass": False,
                "detail": (
                    "等待阻力区触发"
                    if direction == "short" and zones["resistance"]
                    else "尚无高质量阻力聚类"
                    if direction == "short"
                    else "等待支撑区触发"
                    if zones["support"]
                    else "尚无高质量支撑聚类"
                ),
            },
            {
                "key": "trigger",
                "label": "扫损回收",
                "pass": False,
                "detail": "尚未出现完整触发K线",
            },
            {
                "key": "execution",
                "label": "成本与空间",
                "pass": False,
                "detail": "触发后计算",
            },
            {
                "key": "volume",
                "label": "免费量能",
                "pass": False,
                "detail": "仅作辅助加分",
            },
        ],
        "message": (
            "趋势不统一，禁止猜方向"
            if direction == "neutral"
            else "趋势背景已选定，但关键位与扫损回收尚未完成"
        ),
    }


def evaluate_scalp_strategy(
    ticker: Any,
    frames: dict[str, Any],
    candles: dict[str, list[Candle]],
    pivots: dict[str, float | int] | None,
    volume_proxy: dict[str, Any] | None,
) -> dict[str, Any]:
    completed_one = _completed(candles.get("1m", []))
    trigger_candle = completed_one[-1] if completed_one else None
    atr1_values = atr_series(completed_one)
    atr1 = atr1_values[-1] if atr1_values else 0.0
    atr5 = frames["5m"].atr14 if "5m" in frames else atr1 * 3
    spread = max(float(ticker.spread), 0.01)
    tolerance = max(atr5 * 0.22, spread * 4, 0.18)
    trend = trend_context(candles)
    zones = build_zones(candles, pivots, float(ticker.last), tolerance)
    if trigger_candle is None or not atr1 or trend["bias"] == "neutral":
        return _neutral_result(trend, zones, atr1, tolerance)

    direction = trend["bias"]
    zone = zones["support"] if direction == "long" else zones["resistance"]
    trigger = sweep_trigger(trigger_candle, zone, direction, atr1)
    if zone is None or not trigger["valid"]:
        result = _neutral_result(trend, zones, atr1, tolerance)
        result["checklist"][1] = {
            "key": "zone",
            "label": "关键位区域",
            "pass": bool(zone and zone["quality"]),
            "detail": (
                f"{zone['lower']:.2f}–{zone['upper']:.2f}，"
                f"{'+'.join(zone['sources'])}"
                if zone
                else "尚无多周期关键位聚类"
            ),
        }
        result["checklist"][2]["detail"] = trigger["detail"]
        result["score"] = 25 + (zone["score"] if zone and zone["quality"] else 0)
        return result

    entry_buffer = max(spread * 0.5, 0.02)
    entry = (
        trigger_candle.high + entry_buffer
        if direction == "long"
        else trigger_candle.low - entry_buffer
    )
    stop_buffer = max(atr1 * 0.1, spread)
    stop = (
        trigger_candle.low - stop_buffer
        if direction == "long"
        else trigger_candle.high + stop_buffer
    )
    minimum_risk = spread * 3
    if abs(entry - stop) < minimum_risk:
        stop = entry - minimum_risk if direction == "long" else entry + minimum_risk
    risk = abs(entry - stop)
    target = entry + risk * REWARD_RISK if direction == "long" else entry - risk * REWARD_RISK
    spread_ok = spread <= max(atr1 * 0.18, 0.12)
    risk_ok = risk <= atr1 * 1.6
    opposite_zone = zones["resistance"] if direction == "long" else zones["support"]
    available_room = (
        opposite_zone["lower"] - entry
        if opposite_zone and direction == "long"
        else entry - opposite_zone["upper"]
        if opposite_zone
        else float("inf")
    )
    room_ok = available_room >= risk * 1.4
    execution_ok = spread_ok and risk_ok and room_ok
    trigger_age = max(0.0, ticker.timestamp_ms / 1000 - trigger_candle.timestamp)
    age_ok = trigger_age <= MAX_SIGNAL_AGE_SECONDS
    quote_price = ticker.ask if direction == "long" else ticker.bid
    crossed = quote_price >= entry if direction == "long" else quote_price <= entry
    chased = crossed and (
        quote_price > entry + risk * 0.35
        if direction == "long"
        else quote_price < entry - risk * 0.35
    )
    volume = volume_context(volume_proxy, direction)
    score = (
        25
        + (zone["score"] if zone["quality"] else min(12, zone["score"]))
        + 30
        + (10 if execution_ok and age_ok and not chased else 0)
        + volume["score"]
    )
    eligible = (
        zone["quality"]
        and execution_ok
        and age_ok
        and not chased
        and score >= MIN_SCORE
    )
    state = (
        "avoid"
        if not eligible
        else direction
        if crossed
        else "armed_long"
        if direction == "long"
        else "armed_short"
    )
    label = {
        "long": "做多触发",
        "short": "做空触发",
        "armed_long": "做多准备",
        "armed_short": "做空准备",
        "avoid": "放弃本次",
    }[state]
    execution_details: list[str] = []
    if not spread_ok:
        execution_details.append("点差过大")
    if not risk_ok:
        execution_details.append("触发K线过宽")
    if not room_ok:
        execution_details.append("前方空间不足1.4R")
    if not age_ok:
        execution_details.append("信号已过期")
    if chased:
        execution_details.append("价格已跑远，禁止追单")

    message = (
        f"买价突破 {entry:.2f}，执行做多计划"
        if state == "long"
        else f"卖价跌破 {entry:.2f}，执行做空计划"
        if state == "short"
        else f"等待突破 {entry:.2f}，未触发前不下单"
        if state.startswith("armed")
        else "；".join(execution_details) or "关键条件不完整，放弃本次"
    )
    return {
        "version": "SCALP-1.0-PY",
        "state": state,
        "direction": direction,
        "label": label,
        "score": score,
        "threshold": MIN_SCORE,
        "entry": entry,
        "stop": stop,
        "target": target,
        "risk": risk,
        "rewardRisk": REWARD_RISK,
        "timeoutMinutes": TIMEOUT_MINUTES,
        "triggerTimestamp": trigger_candle.timestamp,
        "signature": f"{direction}:{trigger_candle.timestamp}",
        "atr1": atr1,
        "tolerance": tolerance,
        "trend": trend,
        "zones": zones,
        "volume": volume,
        "checklist": [
            {
                "key": "trend",
                "label": "多周期趋势",
                "pass": True,
                "detail": trend["detail"],
            },
            {
                "key": "zone",
                "label": "关键位区域",
                "pass": zone["quality"],
                "detail": (
                    f"{zone['lower']:.2f}–{zone['upper']:.2f}，"
                    f"{'+'.join(zone['sources'])}"
                ),
            },
            {
                "key": "trigger",
                "label": "扫损回收",
                "pass": True,
                "detail": trigger["detail"],
            },
            {
                "key": "execution",
                "label": "成本与空间",
                "pass": execution_ok and age_ok and not chased,
                "detail": (
                    "；".join(execution_details)
                    if execution_details
                    else f"点差{spread:.2f}，目标空间充足"
                ),
            },
            {
                "key": "volume",
                "label": "免费量能",
                "pass": volume["aligned"],
                "neutral": not volume["aligned"],
                "detail": volume["detail"],
            },
        ],
        "message": message,
    }


def calculate_position_size(
    balance: float,
    risk_percent: float,
    entry: float,
    stop: float,
    contract_unit: float,
) -> dict[str, float]:
    risk_usd = max(0.0, balance * risk_percent / 100.0)
    distance = abs(entry - stop)
    contract = max(0.0, contract_unit)
    size = risk_usd / (distance * contract) if distance > 0 and contract > 0 else 0.0
    return {"riskUsd": risk_usd, "distance": distance, "lots": size}
