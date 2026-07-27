from __future__ import annotations

import argparse
from pathlib import Path

from .api import GateTradFiClient
from .monitor import run_monitor


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="监控 Gate TradFi XAUUSD CFD 实时行情（只读，不下单）"
    )
    parser.add_argument("--symbol", default="XAUUSD", help="TradFi 品种，默认 XAUUSD")
    parser.add_argument(
        "--interval",
        type=float,
        default=5.0,
        help="刷新间隔秒数，默认5秒，最低1秒",
    )
    parser.add_argument("--once", action="store_true", help="只获取一次后退出")
    parser.add_argument("--no-clear", action="store_true", help="刷新时不清屏")
    parser.add_argument("--csv", type=Path, help="把每次报价追加保存到CSV")
    parser.add_argument("--above", type=float, help="价格向上触及该数值时提醒")
    parser.add_argument("--below", type=float, help="价格向下触及该数值时提醒")
    parser.add_argument(
        "--timeout",
        type=float,
        default=8.0,
        help="单次HTTP请求超时秒数，默认8秒",
    )
    parser.add_argument("--web", action="store_true", help="启动本地网页仪表盘")
    parser.add_argument("--host", default="127.0.0.1", help="网页监听地址")
    parser.add_argument("--port", type=int, default=8765, help="网页端口，默认8765")
    parser.add_argument(
        "--no-browser",
        action="store_true",
        help="网页模式启动后不自动打开浏览器",
    )
    parser.add_argument(
        "--quote-interval",
        type=float,
        default=0.25,
        help="网页模式报价刷新秒数，默认0.25秒",
    )
    parser.add_argument(
        "--analysis-interval",
        type=float,
        default=5.0,
        help="网页模式K线和指标刷新秒数，默认5秒",
    )
    parser.add_argument(
        "--wecom-bot",
        action="store_true",
        help="启动企业微信智能机器人长连接，凭证从 WECOM_BOT_ID/WECOM_BOT_SECRET 读取",
    )
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    if args.interval < 1:
        parser.error("--interval 不能小于1秒")
    if args.timeout <= 0:
        parser.error("--timeout 必须大于0")
    if not 1 <= args.port <= 65535:
        parser.error("--port 必须在1到65535之间")
    if args.quote_interval < 0.25:
        parser.error("--quote-interval 不能小于0.25秒，以免超过Gate限频")
    if args.analysis_interval < 2:
        parser.error("--analysis-interval 不能小于2秒")
    if args.above is not None and args.below is not None and args.above <= args.below:
        parser.error("--above 应大于 --below")

    client = GateTradFiClient(timeout=args.timeout)
    try:
        if args.web:
            from .web import run_web_server

            code = run_web_server(
                client=client,
                symbol=args.symbol.upper(),
                quote_interval=args.quote_interval,
                analysis_interval=args.analysis_interval,
                host=args.host,
                port=args.port,
                open_browser=not args.no_browser,
                enable_wecom_bot=args.wecom_bot,
            )
        elif args.wecom_bot:
            from .wecom_bot import run_wecom_bot_service

            code = run_wecom_bot_service(
                client=client,
                symbol=args.symbol.upper(),
                quote_interval=args.quote_interval,
                analysis_interval=args.analysis_interval,
            )
        else:
            code = run_monitor(
                client=client,
                symbol=args.symbol.upper(),
                interval=args.interval,
                once=args.once,
                clear_screen=not args.no_clear,
                csv_path=args.csv,
                above=args.above,
                below=args.below,
            )
    except KeyboardInterrupt:
        print("\n监控已停止。")
        code = 0
    raise SystemExit(code)
