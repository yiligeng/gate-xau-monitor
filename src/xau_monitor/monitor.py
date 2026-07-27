from __future__ import annotations

import csv
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from .api import Candle, GateAPIError, GateTradFiClient, Ticker
from .indicators import FrameAnalysis, analyze_frame


SHANGHAI = ZoneInfo("Asia/Shanghai")


@dataclass(frozen=True)
class Snapshot:
    ticker: Ticker
    frames: dict[str, FrameAnalysis]
    candles: dict[str, list[Candle]]


class AlertState:
    def __init__(self) -> None:
        self.above_triggered = False
        self.below_triggered = False
        self.last_bias: str | None = None


def fetch_snapshot(client: GateTradFiClient, symbol: str) -> Snapshot:
    intervals = ("1m", "5m", "15m")
    with ThreadPoolExecutor(max_workers=4) as pool:
        ticker_future = pool.submit(client.ticker, symbol)
        candle_futures = {
            interval: pool.submit(client.candles, symbol, interval, 200)
            for interval in intervals
        }
        ticker = ticker_future.result()
        candles = {
            interval: future.result()
            for interval, future in candle_futures.items()
        }
        frames = {
            interval: analyze_frame(rows, interval)
            for interval, rows in candles.items()
        }
    return Snapshot(ticker=ticker, frames=frames, candles=candles)


def overall_bias(frames: dict[str, FrameAnalysis]) -> tuple[str, int]:
    weighted_score = (
        frames["1m"].score
        + frames["5m"].score * 2
        + frames["15m"].score * 3
    )
    if weighted_score >= 8:
        return "偏多", weighted_score
    if weighted_score <= -8:
        return "偏空", weighted_score
    return "震荡", weighted_score


def short_term_plan(snapshot: Snapshot) -> list[str]:
    ticker = snapshot.ticker
    one = snapshot.frames["1m"]
    five = snapshot.frames["5m"]
    plan: list[str] = []

    if ticker.last < one.ema20 and five.bias == "偏空":
        plan.append(f"价格位于1分钟EMA20下方；跌破 {one.support:.2f} 留意空头延续")
    elif ticker.last > one.ema20 and five.bias == "偏多":
        plan.append(f"价格位于1分钟EMA20上方；突破 {one.resistance:.2f} 留意多头延续")
    else:
        plan.append(
            f"方向未统一；先观察 {one.support:.2f}–{one.resistance:.2f} 区间突破"
        )

    plan.append(
        f"5分钟 ATR≈{five.atr14:.2f}；当前点差 {ticker.spread:.2f}"
    )
    return plan


def render(snapshot: Snapshot, symbol: str) -> str:
    ticker = snapshot.ticker
    timestamp = datetime.fromtimestamp(ticker.timestamp_ms / 1000, tz=SHANGHAI)
    bias, score = overall_bias(snapshot.frames)
    direction = "▲" if ticker.change_percent >= 0 else "▼"

    lines = [
        f"Gate TradFi {symbol} CFD  {timestamp:%Y-%m-%d %H:%M:%S}  状态: {ticker.status}",
        "=" * 78,
        (
            f"最新 {ticker.last:,.2f}  买 {ticker.bid:,.2f}  卖 {ticker.ask:,.2f}"
            f"  点差 {ticker.spread:.2f}  {direction} {ticker.change_percent:+.2f}%"
        ),
        (
            f"今日 开 {ticker.open:,.2f}  高 {ticker.high:,.2f}"
            f"  低 {ticker.low:,.2f}  昨收 {ticker.previous_close:,.2f}"
        ),
        "",
        "周期   收盘       EMA5       EMA10      EMA20      EMA50      RSI14   ATR14   判断",
        "-" * 78,
    ]
    for interval in ("1m", "5m", "15m"):
        frame = snapshot.frames[interval]
        lines.append(
            f"{interval:<5} {frame.close:>8.2f}  {frame.ema5:>9.2f}  "
            f"{frame.ema10:>9.2f}  {frame.ema20:>9.2f}  {frame.ema50:>9.2f}  "
            f"{frame.rsi14:>6.1f}  {frame.atr14:>6.2f}  {frame.bias}"
        )

    one = snapshot.frames["1m"]
    lines.extend(
        [
            "",
            f"综合结构：{bias}（评分 {score:+d}）",
            f"近端支撑：{one.support:.2f}    近端阻力：{one.resistance:.2f}",
        ]
    )
    lines.extend(f"提示：{item}" for item in short_term_plan(snapshot))
    lines.append("")
    lines.append("只读行情监控，不会下单。Ctrl+C 退出。")
    return "\n".join(lines)


def append_csv(path: Path, snapshot: Snapshot) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    new_file = not path.exists()
    ticker = snapshot.ticker
    with path.open("a", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        if new_file:
            writer.writerow(
                [
                    "timestamp_ms",
                    "last",
                    "bid",
                    "ask",
                    "spread",
                    "change_percent",
                    "bias_1m",
                    "bias_5m",
                    "bias_15m",
                ]
            )
        writer.writerow(
            [
                ticker.timestamp_ms,
                ticker.last,
                ticker.bid,
                ticker.ask,
                ticker.spread,
                ticker.change_percent,
                snapshot.frames["1m"].bias,
                snapshot.frames["5m"].bias,
                snapshot.frames["15m"].bias,
            ]
        )


def alert_messages(
    snapshot: Snapshot,
    state: AlertState,
    above: float | None,
    below: float | None,
) -> list[str]:
    messages: list[str] = []
    price = snapshot.ticker.last
    bias, _ = overall_bias(snapshot.frames)

    if above is not None:
        if price >= above and not state.above_triggered:
            messages.append(f"价格已突破上方提醒位 {above:.2f}，当前 {price:.2f}")
            state.above_triggered = True
        elif price < above:
            state.above_triggered = False

    if below is not None:
        if price <= below and not state.below_triggered:
            messages.append(f"价格已跌破下方提醒位 {below:.2f}，当前 {price:.2f}")
            state.below_triggered = True
        elif price > below:
            state.below_triggered = False

    if state.last_bias is not None and bias != state.last_bias:
        messages.append(f"综合结构由“{state.last_bias}”变为“{bias}”")
    state.last_bias = bias
    return messages


def run_monitor(
    client: GateTradFiClient,
    symbol: str,
    interval: float,
    once: bool,
    clear_screen: bool,
    csv_path: Path | None,
    above: float | None,
    below: float | None,
) -> int:
    state = AlertState()
    consecutive_errors = 0

    while True:
        started = time.monotonic()
        try:
            snapshot = fetch_snapshot(client, symbol)
            consecutive_errors = 0
            if clear_screen and not once:
                os.system("cls" if os.name == "nt" else "clear")
            print(render(snapshot, symbol), flush=True)

            if csv_path is not None:
                append_csv(csv_path, snapshot)

            for message in alert_messages(snapshot, state, above, below):
                print(f"\a提醒：{message}", file=sys.stderr, flush=True)

            if once:
                return 0
        except GateAPIError as exc:
            consecutive_errors += 1
            print(
                f"[{datetime.now(SHANGHAI):%H:%M:%S}] 行情读取失败"
                f"（第{consecutive_errors}次）：{exc}",
                file=sys.stderr,
                flush=True,
            )
            if once:
                return 1

        elapsed = time.monotonic() - started
        time.sleep(max(0.2, interval - elapsed))
