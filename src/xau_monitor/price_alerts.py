from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, time, timedelta, timezone
from decimal import Decimal
from typing import Any
from zoneinfo import ZoneInfo

import psycopg


SHANGHAI = ZoneInfo("Asia/Shanghai")
DEFAULT_APPROACH_DISTANCE = 3.0
DEFAULT_ALERT_LIMIT = 2
DEFAULT_REPEAT_SECONDS = 60


@dataclass(frozen=True)
class ParsedLevelCommand:
    levels: list[float]


@dataclass(frozen=True)
class AlertNotification:
    id: int
    chat_id: str
    market: str
    level: float
    price: float
    distance: float
    alerts_sent: int
    alert_limit: int
    expires_at: datetime


class PriceAlertStore:
    def __init__(self, database_url: str) -> None:
        if not database_url:
            raise RuntimeError("DATABASE_URL is required for price alerts")
        self.database_url = database_url

    def _connect(self) -> psycopg.Connection[Any]:
        return psycopg.connect(
            self.database_url,
            connect_timeout=3,
            application_name="xau-monitor-price-alerts",
        )

    def replace_today_alerts(
        self,
        chat_id: str,
        market: str,
        levels: list[float],
        current_price: float,
        created_by: str,
        source_text: str,
        now: datetime | None = None,
    ) -> list[dict[str, Any]]:
        now = now or utc_now()
        expires_at = beijing_day_end(now)
        unique_levels = dedupe_levels(levels)
        with self._connect() as connection:
            connection.execute(
                """
                UPDATE app.price_alerts
                SET status = 'replaced', updated_at = %s
                WHERE chat_id = %s
                  AND market = %s
                  AND status = 'active'
                  AND expires_at > %s
                """,
                (now, chat_id, market, now),
            )
            rows = []
            for level in unique_levels:
                row = connection.execute(
                    """
                    INSERT INTO app.price_alerts (
                        chat_id, created_by, market, level, created_price, side,
                        approach_distance, alert_limit,
                        source_text, expires_at
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    RETURNING id, level, created_price, side, expires_at
                    """,
                    (
                        chat_id,
                        created_by,
                        market,
                        level,
                        current_price,
                        side_for_level(current_price, level),
                        DEFAULT_APPROACH_DISTANCE,
                        DEFAULT_ALERT_LIMIT,
                        source_text[:500],
                        expires_at,
                    ),
                ).fetchone()
                assert row is not None
                rows.append(
                    {
                        "id": row[0],
                        "level": float(row[1]),
                        "created_price": float(row[2]),
                        "side": row[3],
                        "expires_at": row[4],
                    }
                )
        return rows

    def cancel_today_alerts(
        self,
        chat_id: str,
        market: str,
        now: datetime | None = None,
    ) -> int:
        now = now or utc_now()
        with self._connect() as connection:
            result = connection.execute(
                """
                UPDATE app.price_alerts
                SET status = 'cancelled', updated_at = %s
                WHERE chat_id = %s
                  AND market = %s
                  AND status = 'active'
                  AND expires_at > %s
                """,
                (now, chat_id, market, now),
            )
            return result.rowcount or 0

    def active_alerts(
        self,
        chat_id: str,
        market: str,
        now: datetime | None = None,
    ) -> list[dict[str, Any]]:
        now = now or utc_now()
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT id, level, created_price, side, alerts_sent,
                       alert_limit, expires_at
                FROM app.price_alerts
                WHERE chat_id = %s
                  AND market = %s
                  AND status = 'active'
                  AND expires_at > %s
                ORDER BY level DESC, id
                """,
                (chat_id, market, now),
            ).fetchall()
        return [
            {
                "id": row[0],
                "level": float(row[1]),
                "created_price": float(row[2]),
                "side": row[3],
                "alerts_sent": row[4],
                "alert_limit": row[5],
                "expires_at": row[6],
            }
            for row in rows
        ]

    def chat_summaries(
        self,
        market: str,
        now: datetime | None = None,
    ) -> list[dict[str, Any]]:
        now = now or utc_now()
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT chat_id,
                       count(*) FILTER (
                         WHERE status = 'active' AND expires_at > %s
                       ) AS active_count,
                       max(created_at) AS last_seen_at
                FROM app.price_alerts
                WHERE market = %s
                  AND created_at > %s
                GROUP BY chat_id
                ORDER BY active_count DESC, last_seen_at DESC
                LIMIT 20
                """,
                (now, market, now - timedelta(days=7)),
            ).fetchall()
        return [
            {
                "chat_id": row[0],
                "label": mask_chat_id(str(row[0])),
                "active_count": int(row[1] or 0),
                "last_seen_at": row[2],
            }
            for row in rows
        ]

    def web_state(
        self,
        market: str,
        current_price: float,
        chat_id: str | None = None,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        now = now or utc_now()
        chats = self.chat_summaries(market, now)
        selected_chat_id = chat_id or (chats[0]["chat_id"] if chats else "")
        alerts = (
            self.active_alerts(selected_chat_id, market, now)
            if selected_chat_id
            else []
        )
        for alert in alerts:
            alert["distance"] = abs(current_price - alert["level"])
            alert["breached_if_touched"] = is_breached(alert, current_price)
        return {
            "market": market,
            "current_price": current_price,
            "expires_at": beijing_day_end(now),
            "chats": chats,
            "selected_chat_id": selected_chat_id,
            "alerts": alerts,
        }

    def collect_due_alerts(
        self,
        market: str,
        current_price: float,
        now: datetime | None = None,
        repeat_seconds: int = DEFAULT_REPEAT_SECONDS,
    ) -> list[AlertNotification]:
        now = now or utc_now()
        repeat_after = now - timedelta(seconds=repeat_seconds)
        notifications: list[AlertNotification] = []
        with self._connect() as connection:
            connection.execute(
                """
                UPDATE app.price_alerts
                SET status = 'expired', updated_at = %s
                WHERE status = 'active'
                  AND expires_at <= %s
                """,
                (now, now),
            )
            rows = connection.execute(
                """
                SELECT id, chat_id, market, level, created_price, side,
                       approach_distance, alert_limit,
                       alerts_sent, last_alert_at, expires_at
                FROM app.price_alerts
                WHERE market = %s
                  AND status = 'active'
                  AND expires_at > %s
                ORDER BY id
                FOR UPDATE SKIP LOCKED
                """,
                (market, now),
            ).fetchall()
            for row in rows:
                alert = {
                    "id": row[0],
                    "chat_id": row[1],
                    "market": row[2],
                    "level": float(row[3]),
                    "created_price": float(row[4]),
                    "side": row[5],
                    "approach_distance": float(row[6]),
                    "alert_limit": int(row[7]),
                    "alerts_sent": int(row[8]),
                    "last_alert_at": row[9],
                    "expires_at": row[10],
                }
                if is_breached(alert, current_price):
                    connection.execute(
                        """
                        UPDATE app.price_alerts
                        SET status = 'breached',
                            breached_at = %s,
                            updated_at = %s
                        WHERE id = %s
                        """,
                        (now, now, alert["id"]),
                    )
                    continue
                if not should_alert(alert, current_price, repeat_after):
                    continue
                next_count = alert["alerts_sent"] + 1
                connection.execute(
                    """
                    UPDATE app.price_alerts
                    SET alerts_sent = %s,
                        last_alert_at = %s,
                        updated_at = %s
                    WHERE id = %s
                    """,
                    (next_count, now, now, alert["id"]),
                )
                notifications.append(
                    AlertNotification(
                        id=alert["id"],
                        chat_id=alert["chat_id"],
                        market=alert["market"],
                        level=alert["level"],
                        price=current_price,
                        distance=abs(current_price - alert["level"]),
                        alerts_sent=next_count,
                        alert_limit=alert["alert_limit"],
                        expires_at=alert["expires_at"],
                    )
                )
        return notifications


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def beijing_day_end(now: datetime) -> datetime:
    local_now = now.astimezone(SHANGHAI)
    next_day = local_now.date() + timedelta(days=1)
    return datetime.combine(next_day, time.min, tzinfo=SHANGHAI)


def parse_today_levels_command(text: str) -> ParsedLevelCommand | None:
    if "今日点位" not in text:
        return None
    tail = text.split("今日点位", 1)[1]
    matches = re.findall(r"(?<![\w.])-?\d+(?:,\d{3})*(?:\.\d+)?", tail)
    levels = []
    for match in matches:
        value = float(match.replace(",", ""))
        if value > 0:
            levels.append(value)
    return ParsedLevelCommand(levels=dedupe_levels(levels))


def dedupe_levels(levels: list[float]) -> list[float]:
    output: list[float] = []
    seen: set[Decimal] = set()
    for level in levels:
        normalized = Decimal(str(level)).quantize(Decimal("0.01"))
        if normalized in seen:
            continue
        seen.add(normalized)
        output.append(float(normalized))
    return output


def mask_chat_id(chat_id: str) -> str:
    if len(chat_id) <= 10:
        return chat_id
    return f"{chat_id[:6]}...{chat_id[-4:]}"


def side_for_level(current_price: float, level: float) -> str:
    if level > current_price:
        return "above"
    if level < current_price:
        return "below"
    return "at"


def is_breached(alert: dict[str, Any], current_price: float) -> bool:
    level = float(alert["level"])
    side = alert["side"]
    if side == "below":
        return current_price <= level
    if side == "above":
        return current_price >= level
    return True


def should_alert(
    alert: dict[str, Any],
    current_price: float,
    repeat_after: datetime,
) -> bool:
    if int(alert["alerts_sent"]) >= int(alert["alert_limit"]):
        return False
    if abs(current_price - float(alert["level"])) > float(alert["approach_distance"]):
        return False
    last_alert_at = alert.get("last_alert_at")
    return last_alert_at is None or last_alert_at <= repeat_after
