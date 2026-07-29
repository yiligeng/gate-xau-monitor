from __future__ import annotations

import base64
import binascii
import re
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from decimal import Decimal
from typing import Any
from zoneinfo import ZoneInfo

import psycopg


SHANGHAI = ZoneInfo("Asia/Shanghai")
DEFAULT_APPROACH_DISTANCE = 3.0
DEFAULT_ALERT_LIMIT = 3
DEFAULT_REPEAT_SECONDS = 60
POINT_STRATEGY_VERSION = "LEVEL-5X5-V1"
POINT_STRATEGY_RISK = Decimal("5.00")
POINT_STRATEGY_REWARD = Decimal("5.00")
PRICE_PRECISION = Decimal("0.01")
POINT_STRATEGY_DIRECTIONS = {"long", "short"}
POINT_STRATEGY_STATUSES = {
    "pending",
    "open",
    "win",
    "loss",
    "ambiguous",
    "expired",
    "replaced",
    "cancelled",
}
DASHBOARD_DAY_WINDOWS = {7, 30, 90, 365}


@dataclass(frozen=True)
class ParsedLevelCommand:
    levels: list[float]


@dataclass(frozen=True)
class ParsedLevelRangeCommand:
    values: list[float]

    @property
    def has_range(self) -> bool:
        return len(self.values) >= 2

    @property
    def lower(self) -> float:
        return min(self.values[:2])

    @property
    def upper(self) -> float:
        return max(self.values[:2])


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
    event: str
    stage: int


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
        desired_levels = {
            Decimal(str(level)).quantize(PRICE_PRECISION) for level in unique_levels
        }
        local_now = now.astimezone(SHANGHAI)
        day_start = local_now.replace(hour=0, minute=0, second=0, microsecond=0)
        day_end = day_start + timedelta(days=1)
        with self._connect() as connection:
            existing_rows = connection.execute(
                """
                SELECT alert.id, alert.level, alert.created_price, alert.side,
                       alert.expires_at,
                       trial.direction, trial.entry_price, trial.stop_loss,
                       trial.take_profit, trial.status
                FROM app.price_alerts AS alert
                LEFT JOIN app.point_strategy_trials AS trial
                  ON trial.price_alert_id = alert.id
                WHERE alert.chat_id = %s
                  AND alert.market = %s
                  AND alert.created_at >= %s
                  AND alert.created_at < %s
                ORDER BY alert.created_at ASC, alert.id ASC
                """,
                (chat_id, market, day_start, day_end),
            ).fetchall()
            existing_by_level = {}
            for row in existing_rows:
                normalized_level = Decimal(str(row[1])).quantize(PRICE_PRECISION)
                if normalized_level not in desired_levels:
                    continue
                existing_by_level.setdefault(
                    normalized_level,
                    {
                        "id": row[0],
                        "level": float(row[1]),
                        "created_price": float(row[2]),
                        "side": row[3],
                        "expires_at": row[4],
                        "strategy": (
                            {
                                "direction": row[5],
                                "entry_price": float(row[6]),
                                "stop_loss": float(row[7]),
                                "take_profit": float(row[8]),
                                "status": row[9],
                            }
                            if row[5] is not None
                            else None
                        ),
                    },
                )
            keep_levels = set(existing_by_level)
            replace_placeholders = ", ".join(["%s"] * len(desired_levels))
            connection.execute(
                f"""
                WITH replaced AS (
                    UPDATE app.price_alerts
                    SET status = 'replaced', updated_at = %s
                    WHERE chat_id = %s
                      AND market = %s
                      AND status = 'active'
                      AND expires_at > %s
                      AND ROUND(level::numeric, 2) NOT IN ({replace_placeholders})
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
                (now, chat_id, market, now, *desired_levels, now, now),
            )
            rows = []
            for level in unique_levels:
                normalized_level = Decimal(str(level)).quantize(PRICE_PRECISION)
                if normalized_level in keep_levels:
                    rows.append(existing_by_level[normalized_level])
                    continue
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
                            entry_expires_at, setup_day
                        )
                        VALUES (
                            %s, %s, %s, %s, %s, %s, %s,
                            %s, %s, %s, %s, %s, %s
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
                            now.astimezone(SHANGHAI).date(),
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

    def mark_today_alerts_breached(
        self,
        chat_id: str,
        market: str,
        lower: float,
        upper: float,
        now: datetime | None = None,
    ) -> int:
        now = now or utc_now()
        lower, upper = sorted((lower, upper))
        with self._connect() as connection:
            result = connection.execute(
                """
                WITH marked AS (
                    UPDATE app.price_alerts
                    SET status = 'breached',
                        alerts_sent = alert_limit,
                        last_alert_at = %s,
                        breached_at = COALESCE(breached_at, %s),
                        updated_at = %s
                    WHERE chat_id = %s
                      AND market = %s
                      AND status = 'active'
                      AND expires_at > %s
                      AND level >= %s
                      AND level <= %s
                    RETURNING id
                ),
                closed_trials AS (
                    UPDATE app.point_strategy_trials AS trial
                    SET status = 'cancelled',
                        resolved_at = %s,
                        updated_at = %s
                    FROM marked
                    WHERE trial.price_alert_id = marked.id
                      AND trial.status = 'pending'
                    RETURNING trial.id
                )
                SELECT count(*) FROM marked
                """,
                (now, now, now, chat_id, market, now, lower, upper, now, now),
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

    def today_alerts(
        self,
        chat_id: str,
        market: str,
        now: datetime | None = None,
    ) -> list[dict[str, Any]]:
        now = now or utc_now()
        local_now = now.astimezone(SHANGHAI)
        day_start = local_now.replace(hour=0, minute=0, second=0, microsecond=0)
        day_end = day_start + timedelta(days=1)
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT alert.id, alert.level, alert.created_price, alert.side,
                       alert.alerts_sent, alert.alert_limit, alert.expires_at,
                       alert.status, alert.created_at, alert.last_alert_at,
                       alert.breached_at,
                       trial.direction, trial.entry_price, trial.stop_loss,
                       trial.take_profit, trial.status
                FROM app.price_alerts AS alert
                LEFT JOIN app.point_strategy_trials AS trial
                  ON trial.price_alert_id = alert.id
                WHERE alert.chat_id = %s
                  AND alert.market = %s
                  AND alert.created_at >= %s
                  AND alert.created_at < %s
                ORDER BY alert.level DESC, alert.id DESC
                """,
                (chat_id, market, day_start, day_end),
            ).fetchall()
        return [
            {
                "id": row[0],
                "level": float(row[1]),
                "created_price": float(row[2]),
                "side": row[3],
                "alerts_sent": int(row[4]),
                "alert_limit": int(row[5]),
                "expires_at": row[6],
                "status": row[7],
                "created_at": row[8],
                "last_alert_at": row[9],
                "breached_at": row[10],
                "strategy": (
                    {
                        "direction": row[11],
                        "entry_price": float(row[12]),
                        "stop_loss": float(row[13]),
                        "take_profit": float(row[14]),
                        "status": row[15],
                    }
                    if row[11] is not None
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
        direction: str | None = None,
    ) -> dict[str, Any]:
        if not chat_id:
            return empty_strategy_stats()
        normalized_direction = normalize_strategy_direction(direction)
        direction_condition = (
            "\n                  AND direction = %s"
            if normalized_direction
            else ""
        )
        query_parameters: list[Any] = [
            chat_id,
            market,
            POINT_STRATEGY_VERSION,
        ]
        if normalized_direction:
            query_parameters.append(normalized_direction)
        limit = max(0, min(int(recent_limit), 50))
        with self._connect() as connection:
            aggregate = connection.execute(
                f"""
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
                    max(resolved_at) AS last_resolved_at,
                    count(*) FILTER (
                        WHERE status = 'ambiguous'
                    ) AS ambiguous_count
                FROM app.point_strategy_trials
                WHERE chat_id = %s
                  AND market = %s
                  AND strategy_version = %s
                  {direction_condition}
                """,
                tuple(query_parameters),
            ).fetchone()
            direction_rows = connection.execute(
                f"""
                SELECT direction,
                       count(*) FILTER (WHERE status = 'win') AS wins,
                       count(*) FILTER (WHERE status = 'loss') AS losses
                FROM app.point_strategy_trials
                WHERE chat_id = %s
                  AND market = %s
                  AND strategy_version = %s
                  {direction_condition}
                GROUP BY direction
                ORDER BY direction
                """,
                tuple(query_parameters),
            ).fetchall()
            recent_rows = []
            if limit:
                recent_rows = connection.execute(
                    f"""
                    SELECT id, direction, initial_price, entry_price,
                           stop_loss, take_profit, status,
                           trigger_observed_price, exit_observed_price,
                           created_at, triggered_at, resolved_at,
                           resolution_source, ambiguity_reason
                    FROM app.point_strategy_trials
                    WHERE chat_id = %s
                      AND market = %s
                      AND strategy_version = %s
                      {direction_condition}
                    ORDER BY
                        COALESCE(resolved_at, triggered_at, created_at) DESC,
                        id DESC
                    LIMIT %s
                    """,
                    tuple(query_parameters + [limit]),
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
            "ambiguous": int(aggregate[10] or 0) if aggregate else 0,
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
                    "resolution_source": row[12],
                    "ambiguity_reason": row[13],
                }
                for row in recent_rows
            ],
        }

    def strategy_dashboard(
        self,
        chat_id: str,
        market: str,
        *,
        days: int = 30,
        direction: str | None = None,
        status: str | None = None,
        setup_day: date | str | None = None,
        cursor: str | None = None,
        limit: int = 20,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        if not chat_id:
            raise ValueError("chat_id is required")
        if days not in DASHBOARD_DAY_WINDOWS:
            raise ValueError("unsupported day window")
        normalized_direction = normalize_strategy_direction(direction)
        normalized_status = normalize_strategy_status(status)
        normalized_day = normalize_setup_day(setup_day)
        cursor_id = decode_trial_cursor(cursor) if cursor else None
        page_limit = max(1, min(int(limit), 100))
        now = now or utc_now()
        today = now.astimezone(SHANGHAI).date()
        cutoff_day = today - timedelta(days=days - 1)

        summary = self.strategy_stats(
            chat_id,
            market,
            recent_limit=0,
            direction=normalized_direction,
        )
        daily_conditions = [
            "chat_id = %s",
            "market = %s",
            "strategy_version = %s",
            "setup_day >= %s",
        ]
        daily_parameters: list[Any] = [
            chat_id,
            market,
            POINT_STRATEGY_VERSION,
            cutoff_day,
        ]
        if normalized_direction:
            daily_conditions.append("direction = %s")
            daily_parameters.append(normalized_direction)

        detail_conditions = [
            "chat_id = %s",
            "market = %s",
            "strategy_version = %s",
        ]
        detail_parameters: list[Any] = [
            chat_id,
            market,
            POINT_STRATEGY_VERSION,
        ]
        if normalized_direction:
            detail_conditions.append("direction = %s")
            detail_parameters.append(normalized_direction)
        if normalized_status:
            detail_conditions.append("status = %s")
            detail_parameters.append(normalized_status)
        if normalized_day:
            detail_conditions.append("setup_day = %s")
            detail_parameters.append(normalized_day)
        if cursor_id is not None:
            detail_conditions.append("id < %s")
            detail_parameters.append(cursor_id)

        with self._connect() as connection:
            daily_rows = connection.execute(
                f"""
                SELECT
                    setup_day,
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
                    count(*) FILTER (
                        WHERE status = 'ambiguous'
                    ) AS ambiguous_count
                FROM app.point_strategy_trials
                WHERE {" AND ".join(daily_conditions)}
                GROUP BY setup_day
                ORDER BY setup_day
                """,
                tuple(daily_parameters),
            ).fetchall()
            detail_rows = connection.execute(
                f"""
                SELECT id, setup_day, direction, initial_price, entry_price,
                       stop_loss, take_profit, status,
                       trigger_observed_price, exit_observed_price,
                       created_at, triggered_at, resolved_at,
                       resolution_source, ambiguity_reason
                FROM app.point_strategy_trials
                WHERE {" AND ".join(detail_conditions)}
                ORDER BY id DESC
                LIMIT %s
                """,
                tuple(detail_parameters + [page_limit + 1]),
            ).fetchall()

        daily = []
        for row in daily_rows:
            wins = int(row[1] or 0)
            losses = int(row[2] or 0)
            settled = wins + losses
            net_points = float(row[8] or 0)
            daily.append(
                {
                    "setup_day": row[0],
                    "wins": wins,
                    "losses": losses,
                    "settled": settled,
                    "win_rate": wins / settled * 100 if settled else None,
                    "open": int(row[3] or 0),
                    "pending": int(row[4] or 0),
                    "ambiguous": int(row[9] or 0),
                    "expired": int(row[5] or 0),
                    "replaced": int(row[6] or 0),
                    "cancelled": int(row[7] or 0),
                    "net_points": net_points,
                    "expectancy_points": (
                        net_points / settled if settled else None
                    ),
                }
            )

        has_more = len(detail_rows) > page_limit
        page_rows = detail_rows[:page_limit]
        trials = [
            {
                "id": row[0],
                "setup_day": row[1],
                "direction": row[2],
                "initial_price": float(row[3]),
                "entry_price": float(row[4]),
                "stop_loss": float(row[5]),
                "take_profit": float(row[6]),
                "status": row[7],
                "trigger_observed_price": (
                    float(row[8]) if row[8] is not None else None
                ),
                "exit_observed_price": (
                    float(row[9]) if row[9] is not None else None
                ),
                "created_at": row[10],
                "triggered_at": row[11],
                "resolved_at": row[12],
                "resolution_source": row[13],
                "ambiguity_reason": row[14],
            }
            for row in page_rows
        ]
        return {
            "generated_at": now,
            "daily_timezone": "Asia/Shanghai",
            "daily_grain": "setup_day",
            "days": days,
            "summary": summary,
            "daily": daily,
            "trials": trials,
            "page": {
                "limit": page_limit,
                "has_more": has_more,
                "next_cursor": (
                    encode_trial_cursor(int(page_rows[-1][0]))
                    if has_more and page_rows
                    else None
                ),
            },
            "filters": {
                "direction": normalized_direction,
                "status": normalized_status,
                "setup_day": normalized_day,
            },
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
        today_alerts = (
            self.today_alerts(selected_chat_id, market, now)
            if selected_chat_id
            else []
        )
        for alert in alerts:
            alert["distance"] = abs(current_price - alert["level"])
            alert["breached_if_touched"] = is_breached(alert, current_price)
        for alert in today_alerts:
            alert["distance"] = abs(current_price - alert["level"])
        strategy = self.strategy_stats(selected_chat_id, market)
        return {
            "market": market,
            "current_price": current_price,
            "expires_at": beijing_day_end(now),
            "chats": chats,
            "selected_chat_id": selected_chat_id,
            "alerts": alerts,
            "today_alerts": today_alerts,
            "strategy": strategy,
        }

    def reconcile_strategy_candles(
        self,
        market: str,
        candles: list[Any],
        now: datetime | None = None,
    ) -> dict[str, Any]:
        now = now or utc_now()
        ordered_candles = sorted(candles, key=lambda item: int(item.timestamp))
        result: dict[str, Any] = {
            "opened": 0,
            "won": 0,
            "lost": 0,
            "ambiguous": 0,
            "notifications": [],
        }
        if not ordered_candles:
            return result

        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT id, price_alert_id, status, direction, entry_price,
                       stop_loss, take_profit, triggered_at, entry_expires_at,
                       strategy_reconciled_at
                FROM app.point_strategy_trials
                WHERE market = %s
                  AND status IN ('pending', 'open')
                ORDER BY id
                FOR UPDATE SKIP LOCKED
                """,
                (market,),
            ).fetchall()
            for row in rows:
                trial = {
                    "status": str(row[2]),
                    "direction": str(row[3]),
                    "entry_price": float(row[4]),
                    "stop_loss": float(row[5]),
                    "take_profit": float(row[6]),
                }
                status = trial["status"]
                triggered_at = row[7]
                entry_expires_at = row[8]
                reconciled_at = row[9]
                trigger_price: float | None = None
                exit_price: float | None = None
                event_at: datetime | None = None
                ambiguity_reason: str | None = None
                state_changed = False

                for candle in ordered_candles:
                    candle_start = datetime.fromtimestamp(
                        int(candle.timestamp),
                        tz=timezone.utc,
                    )
                    candle_end = candle_start + timedelta(seconds=1)
                    if reconciled_at and candle_end <= reconciled_at:
                        continue
                    if candle_start > now:
                        break
                    current_status = status
                    next_status, next_reason = strategy_status_for_candle(
                        trial | {"status": current_status},
                        candle,
                    )
                    if current_status == "pending":
                        if candle_start >= entry_expires_at:
                            break
                        if next_status == "pending":
                            continue
                        status = next_status
                        triggered_at = candle_end
                        trigger_price = trial["entry_price"]
                        event_at = candle_end
                        ambiguity_reason = next_reason
                        state_changed = True
                        if status == "loss":
                            exit_price = trial["stop_loss"]
                            break
                        if status == "ambiguous":
                            break
                        continue

                    if next_status == "open":
                        continue
                    status = next_status
                    event_at = candle_end
                    ambiguity_reason = next_reason
                    state_changed = True
                    if status == "loss":
                        exit_price = trial["stop_loss"]
                    elif status == "win":
                        exit_price = trial["take_profit"]
                    break

                if not state_changed or event_at is None:
                    continue
                terminal = status in {"win", "loss", "ambiguous"}
                connection.execute(
                    """
                    UPDATE app.point_strategy_trials
                    SET status = %s,
                        trigger_observed_price = COALESCE(
                            trigger_observed_price,
                            %s
                        ),
                        exit_observed_price = %s,
                        triggered_at = COALESCE(triggered_at, %s),
                        resolved_at = %s,
                        strategy_reconciled_at = %s,
                        resolution_source = 'gate_1s_kline',
                        ambiguity_reason = %s,
                        updated_at = %s
                    WHERE id = %s
                    """,
                    (
                        status,
                        trigger_price,
                        exit_price,
                        triggered_at,
                        event_at if terminal else None,
                        event_at,
                        ambiguity_reason,
                        now,
                        row[0],
                    ),
                )
                if triggered_at is not None and trial["status"] == "pending":
                    alert_row = connection.execute(
                        """
                        SELECT id, chat_id, market, level, alert_limit,
                               expires_at
                        FROM app.price_alerts
                        WHERE id = %s
                          AND status = 'active'
                        FOR UPDATE
                        """,
                        (row[1],),
                    ).fetchone()
                    if alert_row is not None:
                        result["notifications"].append(
                            AlertNotification(
                                id=alert_row[0],
                                chat_id=alert_row[1],
                                market=alert_row[2],
                                level=float(alert_row[3]),
                                price=float(trigger_price or trial["entry_price"]),
                                distance=0.0,
                                alerts_sent=int(alert_row[4]),
                                alert_limit=int(alert_row[4]),
                                expires_at=alert_row[5],
                                event="breached",
                                stage=int(alert_row[4]),
                            )
                        )
                result[
                    {
                        "open": "opened",
                        "win": "won",
                        "loss": "lost",
                        "ambiguous": "ambiguous",
                    }[status]
                ] += 1
        return result

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
            reconciled_rows = connection.execute(
                """
                SELECT alert.id, alert.chat_id, alert.market, alert.level,
                       alert.alert_limit, alert.expires_at,
                       COALESCE(
                           trial.trigger_observed_price,
                           trial.entry_price
                       ) AS trigger_price
                FROM app.price_alerts AS alert
                JOIN app.point_strategy_trials AS trial
                  ON trial.price_alert_id = alert.id
                WHERE alert.market = %s
                  AND alert.status = 'active'
                  AND alert.expires_at > %s
                  AND trial.status IN ('open', 'win', 'loss', 'ambiguous')
                  AND trial.triggered_at IS NOT NULL
                ORDER BY alert.id
                FOR UPDATE OF alert SKIP LOCKED
                """,
                (market, now),
            ).fetchall()
            for row in reconciled_rows:
                final_stage = int(row[4])
                notifications.append(
                    AlertNotification(
                        id=row[0],
                        chat_id=row[1],
                        market=row[2],
                        level=float(row[3]),
                        price=float(row[6]),
                        distance=0.0,
                        alerts_sent=final_stage,
                        alert_limit=final_stage,
                        expires_at=row[5],
                        event="breached",
                        stage=final_stage,
                    )
                )
            rows = connection.execute(
                """
                SELECT id, chat_id, market, level, created_price, side,
                       approach_distance, alert_limit,
                       alerts_sent, last_alert_at, expires_at
                FROM app.price_alerts AS alert
                WHERE alert.market = %s
                  AND alert.status = 'active'
                  AND alert.expires_at > %s
                  AND NOT EXISTS (
                      SELECT 1
                      FROM app.point_strategy_trials AS trial
                      WHERE trial.price_alert_id = alert.id
                        AND trial.status IN (
                            'open',
                            'win',
                            'loss',
                            'ambiguous'
                        )
                        AND trial.triggered_at IS NOT NULL
                  )
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
                    final_stage = int(alert["alert_limit"])
                    notifications.append(
                        AlertNotification(
                            id=alert["id"],
                            chat_id=alert["chat_id"],
                            market=alert["market"],
                            level=alert["level"],
                            price=current_price,
                            distance=abs(current_price - alert["level"]),
                            alerts_sent=final_stage,
                            alert_limit=final_stage,
                            expires_at=alert["expires_at"],
                            event="breached",
                            stage=final_stage,
                        )
                    )
                    continue
                stage = alert_stage(alert, current_price)
                sent = int(alert["alerts_sent"])
                if stage < sent:
                    connection.execute(
                        """
                        UPDATE app.price_alerts
                        SET alerts_sent = %s,
                            last_alert_at = NULL,
                            updated_at = %s
                        WHERE id = %s
                        """,
                        (stage, now, alert["id"]),
                    )
                    sent = stage
                if not should_alert(alert, current_price, repeat_after):
                    continue
                notifications.append(
                    AlertNotification(
                        id=alert["id"],
                        chat_id=alert["chat_id"],
                        market=alert["market"],
                        level=alert["level"],
                        price=current_price,
                        distance=abs(current_price - alert["level"]),
                        alerts_sent=stage,
                        alert_limit=alert["alert_limit"],
                        expires_at=alert["expires_at"],
                        event="approach",
                        stage=stage,
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
                        strategy_reconciled_at = %s,
                        resolution_source = 'gate_last_live',
                        ambiguity_reason = NULL,
                        updated_at = %s
                    WHERE id = %s
                    """,
                    (next_status, current_price, now, now, now, row[0]),
                )
        return notifications

    def confirm_alert_notification(
        self,
        notification: AlertNotification,
        now: datetime | None = None,
    ) -> None:
        now = now or utc_now()
        with self._connect() as connection:
            if notification.event == "breached":
                connection.execute(
                    """
                    UPDATE app.price_alerts
                    SET status = 'breached',
                        alerts_sent = GREATEST(alerts_sent, %s),
                        last_alert_at = %s,
                        breached_at = COALESCE(breached_at, %s),
                        updated_at = %s
                    WHERE id = %s
                      AND status = 'active'
                    """,
                    (notification.stage, now, now, now, notification.id),
                )
                trial_row = connection.execute(
                    """
                    SELECT id, status, direction, entry_price,
                           stop_loss, take_profit
                    FROM app.point_strategy_trials
                    WHERE price_alert_id = %s
                    FOR UPDATE
                    """,
                    (notification.id,),
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
                        notification.price,
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
                                strategy_reconciled_at = %s,
                                resolution_source = 'gate_last_live',
                                ambiguity_reason = NULL,
                                updated_at = %s
                            WHERE id = %s
                            """,
                            (
                                next_status,
                                notification.price,
                                next_status,
                                notification.price,
                                now,
                                next_status,
                                now,
                                now,
                                now,
                                trial_row[0],
                            ),
                        )
                return
            connection.execute(
                """
                UPDATE app.price_alerts
                SET alerts_sent = GREATEST(alerts_sent, %s),
                    last_alert_at = %s,
                    updated_at = %s
                WHERE id = %s
                  AND status = 'active'
                """,
                (notification.stage, now, now, notification.id),
            )


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


def strategy_candle_hits(
    trial: dict[str, Any],
    candle: Any,
) -> dict[str, bool]:
    direction = str(trial["direction"])
    entry = _price_decimal(float(trial["entry_price"]))
    stop_loss = _price_decimal(float(trial["stop_loss"]))
    take_profit = _price_decimal(float(trial["take_profit"]))
    high = _price_decimal(float(candle.high))
    low = _price_decimal(float(candle.low))
    if direction == "long":
        return {
            "entry": low <= entry,
            "loss": low <= stop_loss,
            "win": high >= take_profit,
        }
    if direction == "short":
        return {
            "entry": high >= entry,
            "loss": high >= stop_loss,
            "win": low <= take_profit,
        }
    raise ValueError("invalid trial direction")


def strategy_status_for_candle(
    trial: dict[str, Any],
    candle: Any,
) -> tuple[str, str | None]:
    status = str(trial["status"])
    if status not in {"pending", "open"}:
        return status, None
    hits = strategy_candle_hits(trial, candle)
    if status == "pending":
        if not hits["entry"]:
            return "pending", None
        if hits["loss"] and hits["win"]:
            return (
                "ambiguous",
                "entry_stop_and_take_in_same_one_second_candle",
            )
        if hits["loss"]:
            return "loss", None
        if hits["win"]:
            return (
                "ambiguous",
                "entry_and_take_in_same_one_second_candle",
            )
        return "open", None
    if hits["loss"] and hits["win"]:
        return "ambiguous", "stop_and_take_in_same_one_second_candle"
    if hits["loss"]:
        return "loss", None
    if hits["win"]:
        return "win", None
    return "open", None


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
        "ambiguous": 0,
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


def normalize_strategy_direction(direction: str | None) -> str | None:
    normalized = str(direction or "").strip().lower()
    if not normalized:
        return None
    if normalized not in POINT_STRATEGY_DIRECTIONS:
        raise ValueError("invalid strategy direction")
    return normalized


def normalize_strategy_status(status: str | None) -> str | None:
    normalized = str(status or "").strip().lower()
    if not normalized:
        return None
    if normalized not in POINT_STRATEGY_STATUSES:
        raise ValueError("invalid strategy status")
    return normalized


def normalize_setup_day(value: date | str | None) -> date | None:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value.astimezone(SHANGHAI).date()
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value))
    except ValueError as exc:
        raise ValueError("invalid setup day") from exc


def encode_trial_cursor(trial_id: int) -> str:
    if trial_id <= 0:
        raise ValueError("invalid trial cursor id")
    payload = f"trial:{trial_id}".encode("ascii")
    return base64.urlsafe_b64encode(payload).decode("ascii").rstrip("=")


def decode_trial_cursor(cursor: str) -> int:
    value = str(cursor or "").strip()
    if not value or len(value) > 128:
        raise ValueError("invalid trial cursor")
    padding = "=" * (-len(value) % 4)
    try:
        decoded = base64.b64decode(
            value + padding,
            altchars=b"-_",
            validate=True,
        ).decode("ascii")
    except (binascii.Error, UnicodeDecodeError) as exc:
        raise ValueError("invalid trial cursor") from exc
    prefix, separator, raw_id = decoded.partition(":")
    if separator != ":" or prefix != "trial" or not raw_id.isdigit():
        raise ValueError("invalid trial cursor")
    trial_id = int(raw_id)
    if trial_id <= 0:
        raise ValueError("invalid trial cursor")
    return trial_id


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


def parse_mark_touched_levels_command(text: str) -> ParsedLevelRangeCommand | None:
    if "标记触达点位" not in text:
        return None
    tail = text.split("标记触达点位", 1)[1]
    matches = re.findall(r"(?<![\w.])-?\d+(?:,\d{3})*(?:\.\d+)?", tail)
    values = []
    for match in matches:
        value = float(match.replace(",", ""))
        if value > 0:
            values.append(value)
    return ParsedLevelRangeCommand(values=dedupe_levels(values))


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
    del repeat_after
    stage = alert_stage(alert, current_price)
    if stage <= 0:
        return False
    if stage <= int(alert["alerts_sent"]):
        return False
    return True


def alert_stage(alert: dict[str, Any], current_price: float) -> int:
    distance = abs(current_price - float(alert["level"]))
    if distance <= 2:
        return min(2, int(alert["alert_limit"]))
    if distance <= float(alert["approach_distance"]):
        return 1
    return 0
