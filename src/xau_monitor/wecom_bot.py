from __future__ import annotations

import os
import asyncio
import threading
from datetime import datetime
from typing import TYPE_CHECKING, Any
from zoneinfo import ZoneInfo

from .api import GateTradFiClient
from .price_alerts import (
    AlertNotification,
    PriceAlertStore,
    beijing_day_end,
    parse_today_levels_command,
)

if TYPE_CHECKING:
    from .web import MarketState


SHANGHAI = ZoneInfo("Asia/Shanghai")


class WeComBotConfigError(RuntimeError):
    """Raised when the WeCom bot cannot be started from configuration."""


def _money(value: Any, digits: int = 2) -> str:
    if isinstance(value, int | float):
        return f"{value:,.{digits}f}"
    return "-"


def _direction_label(direction: str | None) -> str:
    return {
        "long": "偏多",
        "short": "偏空",
        "neutral": "中性",
    }.get(direction or "", direction or "-")


def select_market_id(text: str) -> str:
    normalized = text.lower()
    if "btc" in normalized or "比特" in normalized or "永续" in normalized:
        return "btc"
    return "xau"


def is_help_request(text: str) -> bool:
    normalized = text.strip().lower()
    return normalized in {"help", "/help", "帮助", "菜单", "指令"}


def help_message() -> str:
    return "\n".join(
        [
            "可用指令：",
            "- 黄金 / XAU：查看 XAUUSD 快照",
            "- BTC：查看 BTCUSDT 永续快照",
            "- 黄金 今日点位 4093.67 4087.70：设置今天24点前有效的提醒",
            "- 黄金 点位：查看今天全部提醒记录（含已触达）",
            "- 黄金 取消今日点位：清空今天的提醒",
            "- 黄金 胜率：查看正负5美元策略的长期统计",
            "- 帮助：查看这份菜单",
            "",
            "点位规则：距离小于等于3美元提醒，最多2次；触达点位后当天作废。",
            "验证规则：下方点位做多、上方点位做空，触发后止盈止损各5美元。",
            "提示：机器人只读行情和策略摘要，不会下单。",
        ]
    )


def format_market_reply(payload: dict[str, Any]) -> str:
    if not payload.get("ok"):
        return f"行情暂不可用：{payload.get('error', '未知错误')}"

    ticker = payload["ticker"]
    market = payload["market"]
    strategy = payload.get("strategy") or {}
    overall = payload.get("overall") or {}
    feed = payload.get("feed") or {}
    live_volume = payload.get("live_volume") or {}
    updated_at = datetime.fromtimestamp(
        float(payload.get("updated_at") or 0),
        tz=SHANGHAI,
    )

    lines = [
        f"**{market['display_name']}**",
        f"时间：{updated_at:%H:%M:%S}",
        (
            f"最新：{_money(ticker.get('last'))}  "
            f"买/卖：{_money(ticker.get('bid'))}/{_money(ticker.get('ask'))}  "
            f"点差：{_money(ticker.get('spread'))}"
        ),
        (
            f"24h：{_money(ticker.get('low'))} - {_money(ticker.get('high'))}  "
            f"涨跌：{ticker.get('change_percent', 0):+.2f}%"
        ),
        f"综合：{overall.get('bias', '-')}（评分 {overall.get('score', 0):+d}）",
        (
            f"策略：{strategy.get('label', '-')} / "
            f"{_direction_label(strategy.get('direction'))} "
            f"({strategy.get('score', 0)}/{strategy.get('threshold', '-')})"
        ),
        f"结论：{strategy.get('message', '-')}",
    ]

    if strategy.get("entry") is not None:
        lines.append(
            "计划："
            f"入场 {_money(strategy.get('entry'))} / "
            f"止损 {_money(strategy.get('stop'))} / "
            f"目标 {_money(strategy.get('target'))}"
        )

    plan = payload.get("plan") or []
    if plan:
        lines.append("")
        lines.append("观察：")
        lines.extend(f"- {item}" for item in plan[:3])

    if live_volume:
        lines.append(
            "量能："
            f"RVOL {_money(live_volume.get('rvol'), 2)}x，"
            f"主动差 {live_volume.get('delta_percent', 0):+.0f}%"
        )

    lines.append("")
    lines.append(
        f"数据延迟：{feed.get('source_age_ms', '-')}ms；"
        "只读监控，不构成交易建议。"
    )
    return "\n".join(lines)


def market_display_name(market_id: str) -> str:
    return "BTCUSDT 永续" if market_id == "btc" else "XAUUSD 黄金 CFD"


def extract_chat_id(frame: dict[str, Any]) -> str:
    body = frame.get("body", {})
    headers = frame.get("headers", {})
    for container in (
        body,
        headers,
        body.get("chat", {}),
        body.get("chat_info", {}),
        body.get("conversation", {}),
        body.get("group", {}),
        body.get("source", {}),
    ):
        if isinstance(container, dict):
            for key in ("chatid", "chat_id", "conversation_id"):
                value = container.get(key)
                if value:
                    return str(value)
    for container in (
        body,
        body.get("from", {}),
        body.get("sender", {}),
        body.get("user", {}),
    ):
        if isinstance(container, dict):
            for key in ("userid", "user_id", "from_userid"):
                value = container.get(key)
                if value:
                    return str(value)
    return ""


def extract_user_id(frame: dict[str, Any]) -> str:
    body = frame.get("body", {})
    for container in (body, body.get("from", {}), body.get("sender", {})):
        if isinstance(container, dict):
            for key in ("userid", "user_id", "from_userid"):
                value = container.get(key)
                if value:
                    return str(value)
    return ""


def _current_price(states: dict[str, MarketState], market_id: str) -> float | None:
    payload = states[market_id].payload()
    if not payload.get("ok"):
        return None
    return float(payload["ticker"]["last"])


def _format_levels(levels: list[float]) -> str:
    return " ".join(f"{level:,.2f}" for level in levels)


def format_strategy_stats(
    market_id: str,
    stats: dict[str, Any],
) -> str:
    settled = int(stats.get("settled") or 0)
    win_rate = stats.get("win_rate")
    expectancy = stats.get("expectancy_points")
    tracking_since = stats.get("tracking_since")
    lines = [
        f"**{market_display_name(market_id)} ±5点策略统计**",
        (
            f"已结算：{settled} 笔  "
            f"胜/负：{int(stats.get('wins') or 0)}/"
            f"{int(stats.get('losses') or 0)}"
        ),
        (
            f"胜率：{win_rate:.2f}%"
            if win_rate is not None
            else "胜率：暂无已结算样本"
        ),
        (
            f"持仓中：{int(stats.get('open') or 0)}  "
            f"待触发：{int(stats.get('pending') or 0)}  "
            f"顺序待复核：{int(stats.get('ambiguous') or 0)}  "
            f"未触发到期：{int(stats.get('expired') or 0)}"
        ),
        (
            f"累计理论点数：{float(stats.get('net_points') or 0):+.2f}  "
            + (
                f"单笔期望：{float(expectancy):+.2f}"
                if expectancy is not None
                else "单笔期望：-"
            )
        ),
    ]
    if isinstance(tracking_since, datetime):
        lines.append(
            f"开始记录：{tracking_since.astimezone(SHANGHAI):%Y-%m-%d %H:%M}"
        )
    lines.extend(
        [
            "",
            "口径：下方点位做多、上方点位做空；触发后止盈/止损各5美元。",
            "Gate实时价与1秒K线共同校验；同秒先后不明不计胜负。",
            "不含点差、滑点和手续费，不代表实际净收益。",
        ]
    )
    return "\n".join(lines)


def _handle_alert_command(
    text: str,
    frame: dict[str, Any],
    states: dict[str, MarketState],
    alert_store: PriceAlertStore | None,
) -> str | None:
    market_id = select_market_id(text)
    if "取消今日点位" in text:
        if alert_store is None:
            return "点位提醒需要数据库配置，目前只能查询行情。"
        chat_id = extract_chat_id(frame)
        if not chat_id:
            return "没有拿到当前会话ID，暂时不能保存或取消点位。"
        count = alert_store.cancel_today_alerts(chat_id, market_id)
        return f"已取消 {market_display_name(market_id)} 今日点位 {count} 条。"

    parsed = parse_today_levels_command(text)
    if parsed is not None:
        if not parsed.levels:
            return "我看到了“今日点位”，但没识别到价格。格式：黄金 今日点位 4093.67 4087.70"
        if alert_store is None:
            return "点位提醒需要数据库配置，目前只能查询行情。"
        chat_id = extract_chat_id(frame)
        if not chat_id:
            return "没有拿到当前会话ID，暂时不能保存点位。"
        current_price = _current_price(states, market_id)
        if current_price is None:
            return "行情还没初始化，等几秒后再发一次今日点位。"
        rows = alert_store.replace_today_alerts(
            chat_id=chat_id,
            market=market_id,
            levels=parsed.levels,
            current_price=current_price,
            created_by=extract_user_id(frame),
            source_text=text,
        )
        expires_at = beijing_day_end(datetime.now(SHANGHAI))
        return "\n".join(
            [
                f"已设置 {market_display_name(market_id)} 今日点位 {len(rows)} 条。",
                f"当前价：{current_price:,.2f}",
                f"点位：{_format_levels([row['level'] for row in rows])}",
                f"有效期：北京时间 {expires_at:%m-%d %H:%M}",
                "规则：距离<=3提醒，最多2次；触达点位后作废。",
                "验证：下方点位做多、上方点位做空；止盈/止损各5美元。",
            ]
        )

    if "胜率" in text or "点位统计" in text:
        if alert_store is None:
            return "点位策略统计需要数据库配置，目前无法读取。"
        chat_id = extract_chat_id(frame)
        if not chat_id:
            return "没有拿到当前会话ID，暂时不能查看胜率。"
        return format_strategy_stats(
            market_id,
            alert_store.strategy_stats(chat_id, market_id),
        )

    if "点位" in text:
        if alert_store is None:
            return "点位提醒需要数据库配置，目前只能查询行情。"
        chat_id = extract_chat_id(frame)
        if not chat_id:
            return "没有拿到当前会话ID，暂时不能查看点位。"
        rows = alert_store.today_alerts(chat_id, market_id)
        if not rows:
            return f"{market_display_name(market_id)} 今天没有点位记录。"
        status_labels = {
            "active": "监控中",
            "breached": "已触达",
            "expired": "已过期",
            "replaced": "已覆盖",
            "cancelled": "已取消",
        }
        lines = [f"{market_display_name(market_id)} 今日点位记录："]
        for row in rows:
            lines.append(
                f"- {row['level']:,.2f}，"
                f"{status_labels.get(row['status'], row['status'])}，已提醒 "
                f"{row['alerts_sent']}/{row['alert_limit']} 次"
            )
        lines.append(
            f"有效期：北京时间 {rows[0]['expires_at'].astimezone(SHANGHAI):%m-%d %H:%M}"
        )
        return "\n".join(lines)

    return None


def reply_for_text(
    text: str,
    states: dict[str, MarketState],
    alert_store: PriceAlertStore | None = None,
    frame: dict[str, Any] | None = None,
) -> str:
    if is_help_request(text):
        return help_message()
    if frame is not None:
        alert_reply = _handle_alert_command(text, frame, states, alert_store)
        if alert_reply is not None:
            return alert_reply
    market_id = select_market_id(text)
    return format_market_reply(states[market_id].payload())


def format_alert_notification(notification: AlertNotification) -> str:
    if notification.event == "breached":
        title = f"**{market_display_name(notification.market)} 点位已触达**"
        status = "价格已经击穿/触达目标位，本点位今日告警作废。"
    elif notification.stage >= 2:
        title = f"**{market_display_name(notification.market)} 点位二级提醒**"
        status = "距离目标位 <= 2 美元；若未触达并远离，二级提醒次数会恢复。"
    else:
        title = f"**{market_display_name(notification.market)} 点位一级提醒**"
        status = "距离目标位 <= 3 美元；若未触达并远离，一级提醒次数会恢复。"
    return "\n".join(
        [
            title,
            f"当前价：{notification.price:,.2f}",
            f"目标位：{notification.level:,.2f}",
            f"距离：{notification.distance:.2f}",
            f"提醒次数：{notification.alerts_sent}/{notification.alert_limit}",
            status,
            "±5点策略会继续跟踪到止盈或止损。",
        ]
    )


def _require_wecom_config() -> tuple[str, str]:
    bot_id = os.environ.get("WECOM_BOT_ID", "").strip()
    secret = os.environ.get("WECOM_BOT_SECRET", "").strip()
    if not bot_id or not secret:
        raise WeComBotConfigError(
            "请先设置 WECOM_BOT_ID 和 WECOM_BOT_SECRET 环境变量"
        )
    return bot_id, secret


def run_wecom_bot(states: dict[str, MarketState]) -> None:
    bot_id, secret = _require_wecom_config()
    database_url = os.environ.get("DATABASE_URL", "").strip()
    alert_store = PriceAlertStore(database_url) if database_url else None
    try:
        from aibot import WSClient, WSClientOptions, generate_req_id
    except ImportError as exc:
        raise WeComBotConfigError(
            "缺少企业微信智能机器人 SDK，请安装："
            "pip install wecom-aibot-python-sdk"
        ) from exc

    ws_client = WSClient(
        WSClientOptions(
            bot_id=bot_id,
            secret=secret,
        )
    )

    @ws_client.on("authenticated")
    def on_authenticated() -> None:
        print("企业微信智能机器人认证成功。", flush=True)

    @ws_client.on("message.text")
    async def on_text(frame: dict[str, Any]) -> None:
        content = frame.get("body", {}).get("text", {}).get("content", "")
        stream_id = generate_req_id("xau")
        reply = reply_for_text(str(content), states, alert_store, frame)
        await ws_client.reply_stream(frame, stream_id, reply, True)

    @ws_client.on("event.enter_chat")
    async def on_enter_chat(frame: dict[str, Any]) -> None:
        await ws_client.reply_welcome(
            frame,
            {
                "msgtype": "text",
                "text": {
                    "content": "我已接入行情监控。发送“黄金”或“BTC”查看快照。"
                },
            },
        )

    async def alert_loop() -> None:
        if alert_store is None:
            print("未配置 DATABASE_URL，点位提醒功能未启用。", flush=True)
            return
        last_sequences: dict[str, int] = {}
        while True:
            for market_id, state in states.items():
                payload = state.payload()
                if not payload.get("ok"):
                    continue
                sequence = int(payload.get("feed", {}).get("sequence") or 0)
                if last_sequences.get(market_id) == sequence:
                    continue
                last_sequences[market_id] = sequence
                current_price = float(payload["ticker"]["last"])
                notifications = await asyncio.to_thread(
                    alert_store.collect_due_alerts,
                    market_id,
                    current_price,
                )
                for notification in notifications:
                    try:
                        await ws_client.send_message(
                            notification.chat_id,
                            {
                                "msgtype": "markdown",
                                "markdown": {
                                    "content": format_alert_notification(notification)
                                },
                            },
                        )
                        await asyncio.to_thread(
                            alert_store.confirm_alert_notification,
                            notification,
                        )
                    except Exception as exc:
                        print(
                            "企业微信点位提醒发送失败，保留待重试："
                            f"alert_id={notification.id} "
                            f"event={notification.event} "
                            f"stage={notification.stage} "
                            f"error={exc}",
                            flush=True,
                        )
            await asyncio.sleep(0.1)

    async def wick_reconciliation_loop() -> None:
        if alert_store is None:
            return
        candle_client = GateTradFiClient(timeout=8.0, retries=1)
        consecutive_errors = 0
        while True:
            try:
                candles = await asyncio.to_thread(
                    candle_client.candles,
                    "XAUUSD",
                    "1s",
                    200,
                )
                result = await asyncio.to_thread(
                    alert_store.reconcile_strategy_candles,
                    "xau",
                    candles,
                )
                consecutive_errors = 0
                if any(result.values()):
                    print(
                        "黄金1秒插针校验："
                        f"入场 {result['opened']}，"
                        f"胜 {result['won']}，"
                        f"负 {result['lost']}，"
                        f"待复核 {result['ambiguous']}。",
                        flush=True,
                    )
                for notification in result.get("notifications", []):
                    try:
                        await ws_client.send_message(
                            notification.chat_id,
                            {
                                "msgtype": "markdown",
                                "markdown": {
                                    "content": format_alert_notification(notification)
                                },
                            },
                        )
                        await asyncio.to_thread(
                            alert_store.confirm_alert_notification,
                            notification,
                        )
                    except Exception as exc:
                        print(
                            "企业微信插针触达提醒发送失败，保留待重试："
                            f"alert_id={notification.id} "
                            f"error={exc}",
                            flush=True,
                        )
            except Exception as exc:
                consecutive_errors += 1
                if consecutive_errors == 1 or consecutive_errors % 60 == 0:
                    print(
                        "黄金1秒插针校验暂不可用："
                        f"{type(exc).__name__}",
                        flush=True,
                    )
            await asyncio.sleep(1.0)

    async def main() -> None:
        await ws_client.connect()
        asyncio.create_task(alert_loop())
        asyncio.create_task(wick_reconciliation_loop())
        await asyncio.Event().wait()

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(main())
    except KeyboardInterrupt:
        ws_client.disconnect()


def start_wecom_bot_thread(states: dict[str, MarketState]) -> threading.Thread:
    thread = threading.Thread(target=run_wecom_bot, args=(states,), daemon=True)
    thread.start()
    return thread


def run_wecom_bot_service(
    client: GateTradFiClient,
    symbol: str,
    quote_interval: float,
    analysis_interval: float,
) -> int:
    from .web import create_market_states, initialize_market_states, start_market_workers

    states = create_market_states(client, symbol, quote_interval, analysis_interval)
    initialize_market_states(states)
    start_market_workers(states)
    print("行情状态已启动，正在连接企业微信智能机器人。", flush=True)
    try:
        run_wecom_bot(states)
    finally:
        for state in states.values():
            state.stop()
    return 0
