from __future__ import annotations

import argparse
import getpass
import json
import os
import sys

from .auth import AuthError, AuthStore


def _password_from_input(use_stdin: bool, confirmation: bool = True) -> str:
    if use_stdin:
        password = sys.stdin.readline().rstrip("\r\n")
        if not password:
            raise ValueError("没有从标准输入收到密码")
        return password
    password = getpass.getpass("密码：")
    if confirmation:
        repeated = getpass.getpass("再次输入密码：")
        if password != repeated:
            raise ValueError("两次密码不一致")
    return password


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="管理网站数据库用户")
    subparsers = parser.add_subparsers(dest="command", required=True)

    create_parser = subparsers.add_parser("create", help="创建用户")
    create_parser.add_argument("username")
    create_parser.add_argument("--password-stdin", action="store_true")

    reset_parser = subparsers.add_parser("reset-password", help="重置密码")
    reset_parser.add_argument("username")
    reset_parser.add_argument("--password-stdin", action="store_true")

    state_parser = subparsers.add_parser("set-active", help="启用或停用用户")
    state_parser.add_argument("username")
    state_parser.add_argument(
        "state",
        choices=("active", "inactive"),
    )

    subparsers.add_parser("list", help="列出用户（不显示密码）")

    subparsers.add_parser("cleanup", help="清理过期会话")
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    database_url = os.environ.get("DATABASE_URL", "")
    if not database_url:
        parser.error("缺少 DATABASE_URL")
    store = AuthStore(database_url)

    try:
        if args.command == "create":
            password = _password_from_input(args.password_stdin)
            user = store.create_user(args.username, password)
            print(f"已创建用户：{user.username}")
        elif args.command == "reset-password":
            password = _password_from_input(args.password_stdin)
            store.reset_password(args.username, password)
            print(f"已重置密码并撤销所有会话：{args.username}")
        elif args.command == "set-active":
            active = args.state == "active"
            store.set_active(args.username, active)
            print(f"用户 {args.username} 状态：{args.state}")
        elif args.command == "list":
            print(
                json.dumps(
                    store.list_users(),
                    ensure_ascii=False,
                    indent=2,
                    default=str,
                )
            )
        elif args.command == "cleanup":
            store.cleanup()
            print("已清理过期认证记录")
    except (AuthError, ValueError) as exc:
        print(str(exc), file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
