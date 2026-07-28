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
POINT_STRATEGY_VERSION = "LEVEL-5X5-V1"
POINT_STRATEGY_RISK = Decimal("5.00")
POINT_STRATEGY_REWARD = Decimal("5.00")
PRICE_PRECISION = Decimal("0.01")


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
                WITH replaced AS (
                    UPDATE app.price_alerts
                    SET status = 'replaced', updated_at = %s
                    WHERE chat_id = %s
                      AND market = %s
                      AND status = 'active'
                      AND expires_at > %s
                    RETURNING id
                )
                UPDATE app.point_strategy_trials AS trial
                SET status = 'replaced',
                    resolved_at = %s,
                    updated_at = %s
                FROM replaced
                WHERE trial.price_alert_id = replaced.id
                  AND trial.status = 'pending'
                """,
                (now, chat_id, market, now, now, now),
            )
            rows = []
            for level in unique_levels:
                plan = build_point_strategy_plan(current_price, level)
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
                if plan is not None:
                    connection.execute(
                        """
                        INSERT INTO app.point_strategy_trials (
                            price_alert_id, chat_id, market, strategy_version,
                            direction, initial_price, entry_price,
                            stop_loss, take_profit, risk_points, reward_points,
                            entry_expires_at
                        )
                        VALUES (
                            %s, %s, %s, %s, %s, %s, %s,
                            %s, %s, %s, %s, %s
                        )
                        """,
                        (
                            row[0],
                            chat_id,
                            market,
                            POINT_STRATEGY_VERSION,
                            plan["direction"],
                            plan["initial_price"],
                            plan["entry_price"],
                            plan["stop_loss"],
                            plan["take_profit"],
                            float(POINT_STRATEGY_RISK),
                            float(POINT_STRATEGY_REWARD),
                            expires_at,
                        ),
                    )
                rows.append(
                    {
                        "id": row[0],
                        "level": float(row[1]),
                        "created_price": float(row[2]),
                        "side": row[3],
                        "expires_at": row[4],
                        "strategy": plan,
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
                WITH cancelled AS (
                    UPDATE app.price_alerts
                    SET status = 'cancelled', updated_at = %s
                    WHERE chat_id = %s
                      AND market = %s
                      AND status = 'active'
                      AND expires_at > %s
                    RETURNING id
                ),
                closed_trials AS (
                    UPDATE app.point_strategy_trials AS trial
                    SET status = 'cancelled',
                        resolved_at = %s,
                        updated_at = %s
                    FROM cancelled
                    WHERE trial.price_alert_id = cancelled.id
                      AND trial.status = 'pending'
                    RETURNING trial.id
                )
                SELECT count(*) FROM cancelled
                """,
                (now, chat_id, market, now, now, now),
            ).fetchone()
            return int(result[0]) if result else 0

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
                SELECT alert.id, alert.level, alert.created_price, alert.side,
                       alert.alerts_sent, alert.alert_limit, alert.expires_at,
                       trial.direction, trial.entry_price, trial.stop_loss,
                       trial.take_profit, trial.status
                FROM app.price_alerts AS alert
                LEFT JOIN app.point_strategy_trials AS trial
                  ON trial.price_alert_id = alert.id
                WHERE alert.chat_id = %s
                  AND alert.market = %s
                  AND alert.status = 'active'
                  AND alert.expires_at > %s
                ORDER BY alert.level DESC, alert.id
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
                "strategy": (
                    {
                        "direction": row[7],
                        "entry_price": float(row[8]),
                        "stop_loss": float(row[9]),
                        "take_profit": float(row[10]),
                        "status": row[11],
                    }
                    if row[7] is not None
                    else None
                ),
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

    def strategy_stats(
        self,
        chat_id: str,
        market: str,
        recent_limit: int = 12,
    ) -> dict[str, Any]:
        if not chat_id:
            return empty_strategy_stats()
        limit = max(1, min(int(recent_limit), 50))
        with self._connect() as connection:
            aggregate = connection.execute(
                """
                SELECT
                    count(*) FILTER (WHERE status = 'win') AS wins,
                    count(*) FILTER (WHERE status = 'loss') AS losses,
                    count(*) FILTER (WHERE status = 'open') AS open_count,
                    count(*) FILTER (WHERE status = 'pending') AS pending_count,
                    count(*) FILTER (WHERE status = 'expired') AS expired_count,
                    count(*) FILTER (WHERE status = 'replaced') AS replaced_count,
                    count(*) FILTER (WHERE status = 'cancelled') AS cancelled_count,
                    COALESCE(
                        sum(
                            CASE status
                                WHEN 'win' THEN reward_points
                                WHEN 'loss' THEN -risk_points
                                ELSE 0
                            END
                        ),
                        0
                    ) AS net_points,
                    min(created_at) AS tracking_since,
                    max(resolved_at) AS last_resolved_at
                FROM app.point_strategy_trials
                WHERE chat_id = %s
                  AND market = %s
                  AND strategy_version = %s
                """,
                (chat_id, market, POINT_STRATEGY_VERSION),
            ).fetchone()
            direction_rows = connection.execute(
                """
                SELECT direction,
                       count(*) FILTER (WHERE status = 'win') AS wins,
                       count(*) FILTER (WHERE status = 'loss') AS losses
                FROM app.point_strategy_trials
                WHERE chat_id = %s
                  AND market = %s
                  AND strategy_version = %s
                GROUP BY direction
                ORDER BY direction
                """,
                (chat_id, market, POINT_STRATEGY_VERSION),
            ).fetchall()
            recent_rows = connection.execute(
                """
                SELECT id, direction, initial_price, entry_price,
                       stop_loss, take_profit, status,
                       trigger_observed_price, exit_observed_price,
                       created_at, triggered_at, resolved_at
                FROM app.point_strategy_trials
                WHERE chat_id = %s
                  AND market = %s
                  AND strategy_version = %s
                ORDER BY
                    COALESCE(resolved_at, triggered_at, created_at) DESC,
                    id DESC
                LIMIT %s
                """,
                (chat_id, market, POINT_STRATEGY_VERSION, limit),
            ).fetchall()

        wins = int(aggregate[0] or 0) if aggregate else 0
        losses = int(aggregate[1] or 0) if aggregate else 0
        settled = wins + losses
        net_points = float(aggregate[7] or 0) if aggregate else 0.0
        by_direction = {}
        for row in direction_rows:
            direction_wins = int(row[1] or 0)
            direction_losses = int(row[2] or 0)
            direction_settled = direction_wins + direction_losses
            by_direction[str(row[0])] = {
                "wins": direction_wins,
                "losses": direction_losses,
                "settled": direction_settled,
                "win_rate": (
                    direction_wins / direction_settled * 100
                    if direction_settled
                    else None
                ),
            }
        return {
            "strategy_version": POINT_STRATEGY_VERSION,
            "price_basis": "last",
            "risk_points": float(POINT_STRATEGY_RISK),
            "reward_points": float(POINT_STRATEGY_REWARD),
            "wins": wins,
            "losses": losses,
            "settled": settled,
            "win_rate": wins / settled * 100 if settled else None,
            "open": int(aggregate[2] or 0) if aggregate else 0,
            "pending": int(aggregate[3] or 0) if aggregate else 0,
            "expired": int(aggregate[4] or 0) if aggregate else 0,
            "replaced": int(aggregate[5] or 0) if aggregate else 0,
            "cancelled": int(aggregate[6] or 0) if aggregate else 0,
            "net_points": net_points,
            "expectancy_points": net_points / settled if settled else None,
            "tracking_since": aggregate[8] if aggregate else None,
            "last_resolved_at": aggregate[9] if aggregate else None,
            "by_direction": by_direction,
            "recent": [
                {
                    "id": row[0],
                    "direction": row[1],
                    "initial_price": float(row[2]),
                    "entry_price": float(row[3]),
                    "stop_loss": float(row[4]),
                    "take_profit": float(row[5]),
                    "status": row[6],
                    "trigger_observed_price": (
                        float(row[7]) if row[7] is not None else None
                    ),
                    "exit_observed_price": (
                        float(row[8]) if row[8] is not None else None
                    ),
                    "created_at": row[9],
                    "triggered_at": row[10],
                    "resolved_at": row[11],
                }
                for row in recent_rows
            ],
        }

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
        strategy = self.strategy_stats(selected_chat_id, market)
        return {
            "market": market,
            "current_price": current_price,
            "expires_at": beijing_day_end(now),
            "chats": chats,
            "selected_chat_id": selected_chat_id,
            "alerts": alerts,
            "strategy": strategy,
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
                WITH expired AS (
                    UPDATE app.price_alerts
                    SET status = 'expired', updated_at = %s
                    WHERE status = 'active'
                      AND expires_at <= %s
                    RETURNING id
                )
                UPDATE app.point_strategy_trials AS trial
                SET status = 'expired',
                    resolved_at = %s,
                    updated_at = %s
                FROM expired
                WHERE trial.price_alert_id = expired.id
                  AND trial.status = 'pending'
                """,
                (now, now, now, now),
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
                    trial_row = connection.execute(
                        """
                        SELECT id, status, direction, entry_price,
                               stop_loss, take_profit
                        FROM app.point_strategy_trials
                        WHERE price_alert_id = %s
                        FOR UPDATE
                        """,
                        (alert["id"],),
                    ).fetchone()
                    if trial_row is not None and trial_row[1] == "pending":
                        trial = {
                            "status": trial_row[1],
                            "direction": trial_row[2],
                            "entry_price": float(trial_row[3]),
                            "stop_loss": float(trial_row[4]),
                            "take_profit": float(trial_row[5]),
                        }
                        next_status = strategy_status_for_price(
                            trial,
                            current_price,
                        )
                        if next_status in {"open", "loss"}:
                            connection.execute(
                                """
                                UPDATE app.point_strategy_trials
                                SET status = %s,
                                    trigger_observed_price = %s,
                                    exit_observed_price = CASE
                                        WHEN %s = 'loss' THEN %s
                                        ELSE exit_observed_price
                                    END,
                                    triggered_at = %s,
                                    resolved_at = CASE
                                        WHEN %s = 'loss' THEN %s
                                        ELSE resolved_at
                                    END,
                                    updated_at = %s
                                WHERE id = %s
                                """,
                                (
                                    next_status,
                                    current_price,
                                    next_status,
                                    current_price,
                                    now,
                                    next_status,
                                    now,
                                    now,
                                    trial_row[0],
                                ),
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
            open_rows = connection.execute(
                """
                SELECT id, status, direction, entry_price,
                       stop_loss, take_profit
                FROM app.point_strategy_trials
                WHERE market = %s
                  AND status = 'open'
                ORDER BY id
                FOR UPDATE SKIP LOCKED
                """,
                (market,),
            ).fetchall()
            for row in open_rows:
                trial = {
                    "status": row[1],
                    "direction": row[2],
                    "entry_price": float(row[3]),
                    "stop_loss": float(row[4]),
                    "take_profit": float(row[5]),
                }
                next_status = strategy_status_for_price(trial, current_price)
                if next_status not in {"win", "loss"}:
                    continue
                connection.execute(
                    """
                    UPDATE app.point_strategy_trials
                    SET status = %s,
                        exit_observed_price = %s,
                        resolved_at = %s,
                        updated_at = %s
                    WHERE id = %s
                    """,
                    (next_status, current_price, now, now, row[0]),
                )
        return notifications


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def beijing_day_end(now: datetime) -> datetime:
    local_now = now.astimezone(SHANGHAI)
    next_day = local_now.date() + timedelta(days=1)
    return datetime.combine(next_day, time.min, tzinfo=SHANGHAI)


def _price_decimal(value: float | Decimal) -> Decimal:
    return Decimal(str(value)).quantize(PRICE_PRECISION)


def build_point_strategy_plan(
    current_price: float,
    level: float,
) -> dict[str, Any] | None:
    initial = _price_decimal(current_price)
    entry = _price_decimal(level)
    if entry < initial:
        direction = "long"
        stop_loss = entry - POINT_STRATEGY_RISK
        take_profit = entry + POINT_STRATEGY_REWARD
    elif entry > initial:
        direction = "short"
        stop_loss = entry + POINT_STRATEGY_RISK
        take_profit = entry - POINT_STRATEGY_REWARD
    else:
        return None
    return {
        "strategy_version": POINT_STRATEGY_VERSION,
        "price_basis": "last",
        "direction": direction,
        "initial_price": float(initial),
        "entry_price": float(entry),
        "stop_loss": float(stop_loss),
        "take_profit": float(take_profit),
        "risk_points": float(POINT_STRATEGY_RISK),
        "reward_points": float(POINT_STRATEGY_REWARD),
    }


def strategy_status_for_price(
    trial: dict[str, Any],
    current_price: float,
) -> str:
    status = str(trial["status"])
    if status not in {"pending", "open"}:
        return status
    direction = str(trial["direction"])
    price = _price_decimal(current_price)
    entry = _price_decimal(float(trial["entry_price"]))
    stop_loss = _price_decimal(float(trial["stop_loss"]))
    take_profit = _price_decimal(float(trial["take_profit"]))

    if status == "pending":
        triggered = (
            direction == "long" and price <= entry
        ) or (
            direction == "short" and price >= entry
        )
        if not triggered:
            return "pending"
        if (
            direction == "long" and price <= stop_loss
        ) or (
            direction == "short" and price >= stop_loss
        ):
            return "loss"
        return "open"

    if direction == "long":
        if price <= stop_loss:
            return "loss"
        if price >= take_profit:
            return "win"
    elif direction == "short":
        if price >= stop_loss:
            return "loss"
        if price <= take_profit:
            return "win"
    return "open"


def empty_strategy_stats() -> dict[str, Any]:
    return {
        "strategy_version": POINT_STRATEGY_VERSION,
        "price_basis": "last",
        "risk_points": float(POINT_STRATEGY_RISK),
        "reward_points": float(POINT_STRATEGY_REWARD),
        "wins": 0,
        "losses": 0,
        "settled": 0,
        "win_rate": None,
        "open": 0,
        "pending": 0,
        "expired": 0,
        "replaced": 0,
        "cancelled": 0,
        "net_points": 0.0,
        "expectancy_points": None,
        "tracking_since": None,
        "last_resolved_at": None,
        "by_direction": {},
        "recent": [],
    }


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
