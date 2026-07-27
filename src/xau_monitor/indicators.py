from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from .api import Candle


def ema_series(values: Sequence[float], period: int) -> list[float]:
    if period <= 0:
        raise ValueError("period 必须大于0")
    if not values:
        raise ValueError("values 不能为空")

    alpha = 2.0 / (period + 1.0)
    output = [float(values[0])]
    for value in values[1:]:
        output.append(float(value) * alpha + output[-1] * (1.0 - alpha))
    return output


def ema(values: Sequence[float], period: int) -> float:
    return ema_series(values, period)[-1]


def rsi(values: Sequence[float], period: int = 14) -> float:
    if len(values) <= period:
        raise ValueError("计算 RSI 的数据不足")

    changes = [float(values[i]) - float(values[i - 1]) for i in range(1, len(values))]
    gains = [max(change, 0.0) for change in changes]
    losses = [max(-change, 0.0) for change in changes]

    average_gain = sum(gains[:period]) / period
    average_loss = sum(losses[:period]) / period
    for gain, loss in zip(gains[period:], losses[period:]):
        average_gain = (average_gain * (period - 1) + gain) / period
        average_loss = (average_loss * (period - 1) + loss) / period

    if average_loss == 0:
        return 100.0
    relative_strength = average_gain / average_loss
    return 100.0 - 100.0 / (1.0 + relative_strength)


def atr(candles: Sequence[Candle], period: int = 14) -> float:
    if len(candles) <= period:
        raise ValueError("计算 ATR 的数据不足")

    true_ranges: list[float] = []
    for previous, current in zip(candles, candles[1:]):
        true_ranges.append(
            max(
                current.high - current.low,
                abs(current.high - previous.close),
                abs(current.low - previous.close),
            )
        )

    current_atr = sum(true_ranges[:period]) / period
    for true_range in true_ranges[period:]:
        current_atr = (current_atr * (period - 1) + true_range) / period
    return current_atr


@dataclass(frozen=True)
class FrameAnalysis:
    interval: str
    close: float
    ema5: float
    ema10: float
    ema20: float
    ema50: float
    rsi14: float
    atr14: float
    support: float
    resistance: float
    bias: str
    score: int


def analyze_frame(
    candles: Sequence[Candle],
    interval: str,
    level_lookback: int = 20,
) -> FrameAnalysis:
    closes = [candle.close for candle in candles]
    ema5_values = ema_series(closes, 5)
    ema20_values = ema_series(closes, 20)
    ema5_value = ema5_values[-1]
    ema10_value = ema(closes, 10)
    ema20_value = ema20_values[-1]
    ema50_value = ema(closes, 50)
    rsi_value = rsi(closes)

    # 排除仍在形成中的最后一根K线，避免支撑阻力随当前报价跳动。
    completed = list(candles[-(level_lookback + 1) : -1])
    support = min(candle.low for candle in completed)
    resistance = max(candle.high for candle in completed)

    score = 0
    score += 1 if closes[-1] > ema20_value else -1
    score += 1 if ema20_value > ema50_value else -1
    score += 1 if ema5_value > ema10_value else -1
    score += 1 if ema20_values[-1] > ema20_values[-4] else -1
    if rsi_value >= 55:
        score += 1
    elif rsi_value <= 45:
        score -= 1

    if score >= 3:
        bias = "偏多"
    elif score <= -3:
        bias = "偏空"
    else:
        bias = "震荡"

    return FrameAnalysis(
        interval=interval,
        close=closes[-1],
        ema5=ema5_value,
        ema10=ema10_value,
        ema20=ema20_value,
        ema50=ema50_value,
        rsi14=rsi_value,
        atr14=atr(candles),
        support=support,
        resistance=resistance,
        bias=bias,
        score=score,
    )

