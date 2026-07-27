from __future__ import annotations

import base64
import hashlib
import hmac
import ipaddress
import os
import secrets
import unicodedata
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

import psycopg
from psycopg import errors


SESSION_COOKIE = "__Host-sheshe_session"
SESSION_TTL = timedelta(days=7)
PASSWORD_MIN_LENGTH = 12
PASSWORD_MAX_LENGTH = 128
USERNAME_MIN_LENGTH = 1
USERNAME_MAX_LENGTH = 32
SCRYPT_N = 2**14
SCRYPT_R = 8
SCRYPT_P = 1
SCRYPT_LENGTH = 32


class AuthError(Exception):
    pass


class InvalidCredentials(AuthError):
    pass


class InvalidInput(AuthError):
    pass


class DuplicateUsername(AuthError):
    pass


@dataclass(frozen=True)
class AuthUser:
    id: int
    username: str


@dataclass(frozen=True)
class AuthSession:
    user: AuthUser
    raw_token: str
    expires_at: datetime


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def normalize_username(username: str) -> tuple[str, str]:
    normalized = unicodedata.normalize("NFKC", username).strip()
    if not USERNAME_MIN_LENGTH <= len(normalized) <= USERNAME_MAX_LENGTH:
        raise InvalidInput(
            f"用户名需要 {USERNAME_MIN_LENGTH}–{USERNAME_MAX_LENGTH} 个字符"
        )
    if not all(
        character.isascii()
        and (character.isalnum() or character in "._-")
        for character in normalized
    ):
        raise InvalidInput("用户名只能包含英文字母、数字、点、横线和下划线")
    return normalized, normalized.casefold()


def validate_password(password: str) -> None:
    if not PASSWORD_MIN_LENGTH <= len(password) <= PASSWORD_MAX_LENGTH:
        raise InvalidInput(
            f"密码需要 {PASSWORD_MIN_LENGTH}–{PASSWORD_MAX_LENGTH} 个字符"
        )


def hash_password(password: str, salt: bytes | None = None) -> str:
    validate_password(password)
    password_salt = salt or os.urandom(16)
    digest = hashlib.scrypt(
        password.encode("utf-8"),
        salt=password_salt,
        n=SCRYPT_N,
        r=SCRYPT_R,
        p=SCRYPT_P,
        dklen=SCRYPT_LENGTH,
    )
    salt_text = base64.urlsafe_b64encode(password_salt).decode("ascii")
    digest_text = base64.urlsafe_b64encode(digest).decode("ascii")
    return (
        f"scrypt${SCRYPT_N}${SCRYPT_R}${SCRYPT_P}$"
        f"{salt_text}${digest_text}"
    )


def verify_password(password: str, encoded: str) -> bool:
    try:
        algorithm, n_text, r_text, p_text, salt_text, digest_text = (
            encoded.split("$", 5)
        )
        if algorithm != "scrypt":
            return False
        salt = base64.urlsafe_b64decode(salt_text.encode("ascii"))
        expected = base64.urlsafe_b64decode(digest_text.encode("ascii"))
        actual = hashlib.scrypt(
            password.encode("utf-8"),
            salt=salt,
            n=int(n_text),
            r=int(r_text),
            p=int(p_text),
            dklen=len(expected),
        )
        return hmac.compare_digest(actual, expected)
    except (ValueError, TypeError):
        return False


_DUMMY_PASSWORD_HASH = hash_password(
    "this-is-a-dummy-password-that-never-authenticates"
)


def normalize_ip(value: str) -> str:
    try:
        return str(ipaddress.ip_address(value))
    except ValueError:
        return "127.0.0.1"


def token_hash(raw_token: str) -> str:
    return hashlib.sha256(raw_token.encode("ascii")).hexdigest()


class AuthStore:
    def __init__(self, database_url: str) -> None:
        if not database_url:
            raise RuntimeError(
                "DATABASE_URL is required; authentication fails closed"
            )
        self.database_url = database_url

    def _connect(self) -> psycopg.Connection[Any]:
        return psycopg.connect(
            self.database_url,
            connect_timeout=3,
            application_name="xau-monitor-auth",
        )

    def create_user(self, username: str, password: str) -> AuthUser:
        display_name, username_key = normalize_username(username)
        password_hash = hash_password(password)
        try:
            with self._connect() as connection:
                row = connection.execute(
                    """
                    INSERT INTO app.users (
                        username, username_key, password_hash
                    )
                    VALUES (%s, %s, %s)
                    RETURNING id, username
                    """,
                    (display_name, username_key, password_hash),
                ).fetchone()
        except errors.UniqueViolation as exc:
            raise DuplicateUsername("用户名已存在") from exc
        assert row is not None
        return AuthUser(id=row[0], username=row[1])

    def list_users(self) -> list[dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute(
                """
                SELECT id, username, is_active, created_at, last_login_at
                FROM app.users
                ORDER BY id
                """
            ).fetchall()
        return [
            {
                "id": row[0],
                "username": row[1],
                "is_active": row[2],
                "created_at": row[3],
                "last_login_at": row[4],
            }
            for row in rows
        ]

    def set_active(self, username: str, active: bool) -> None:
        _, username_key = normalize_username(username)
        with self._connect() as connection:
            row = connection.execute(
                """
                UPDATE app.users
                SET is_active = %s, updated_at = now()
                WHERE username_key = %s
                RETURNING id
                """,
                (active, username_key),
            ).fetchone()
            if row is None:
                raise InvalidInput("用户不存在")
            if not active:
                connection.execute(
                    "DELETE FROM app.sessions WHERE user_id = %s",
                    (row[0],),
                )

    def reset_password(self, username: str, password: str) -> None:
        _, username_key = normalize_username(username)
        password_hash = hash_password(password)
        with self._connect() as connection:
            row = connection.execute(
                """
                UPDATE app.users
                SET password_hash = %s,
                    password_changed_at = now(),
                    updated_at = now()
                WHERE username_key = %s
                RETURNING id
                """,
                (password_hash, username_key),
            ).fetchone()
            if row is None:
                raise InvalidInput("用户不存在")
            connection.execute(
                "DELETE FROM app.sessions WHERE user_id = %s",
                (row[0],),
            )

    def authenticate(
        self,
        username: str,
        password: str,
        ip_address: str,
        user_agent: str,
    ) -> AuthSession:
        now = utc_now()
        normalized_ip = normalize_ip(ip_address)
        try:
            _, username_key = normalize_username(username)
        except InvalidInput:
            invalid_digest = hashlib.sha256(
                username.encode("utf-8", errors="replace")
            ).hexdigest()
            username_key = f"invalid-{invalid_digest[:24]}"
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT id, username, password_hash, is_active
                FROM app.users
                WHERE username_key = %s
                """,
                (username_key,),
            ).fetchone()
            encoded = row[2] if row is not None else _DUMMY_PASSWORD_HASH
            valid_password = verify_password(password, encoded)
            if row is None or not row[3] or not valid_password:
                raise InvalidCredentials("用户名或密码错误")

            connection.execute(
                """
                UPDATE app.users
                SET last_login_at = %s, updated_at = %s
                WHERE id = %s
                """,
                (now, now, row[0]),
            )
            return self._create_session(
                connection,
                AuthUser(id=row[0], username=row[1]),
                normalized_ip,
                user_agent,
                now,
            )

    def get_session(self, raw_token: str) -> AuthSession | None:
        if not raw_token or len(raw_token) > 256:
            return None
        now = utc_now()
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT u.id, u.username, s.expires_at, s.last_seen_at
                FROM app.sessions AS s
                JOIN app.users AS u ON u.id = s.user_id
                WHERE s.token_hash = %s
                  AND s.expires_at > %s
                  AND u.is_active
                """,
                (token_hash(raw_token), now),
            ).fetchone()
            if row is None:
                return None
            if row[3] < now - timedelta(minutes=5):
                connection.execute(
                    """
                    UPDATE app.sessions
                    SET last_seen_at = %s
                    WHERE token_hash = %s
                    """,
                    (now, token_hash(raw_token)),
                )
            return AuthSession(
                user=AuthUser(id=row[0], username=row[1]),
                raw_token=raw_token,
                expires_at=row[2],
            )

    def logout(self, raw_token: str) -> None:
        if not raw_token or len(raw_token) > 256:
            return
        with self._connect() as connection:
            connection.execute(
                "DELETE FROM app.sessions WHERE token_hash = %s",
                (token_hash(raw_token),),
            )

    def change_credentials(
        self,
        user_id: int,
        current_password: str,
        new_username: str | None,
        new_password: str | None,
        ip_address: str,
        user_agent: str,
    ) -> AuthSession:
        now = utc_now()
        username_update: tuple[str, str] | None = None
        if new_username:
            username_update = normalize_username(new_username)
        if new_password:
            validate_password(new_password)
        if username_update is None and not new_password:
            raise InvalidInput("没有需要修改的内容")

        try:
            with self._connect() as connection:
                row = connection.execute(
                    """
                    SELECT username, password_hash, is_active
                    FROM app.users
                    WHERE id = %s
                    FOR UPDATE
                    """,
                    (user_id,),
                ).fetchone()
                if (
                    row is None
                    or not row[2]
                    or not verify_password(current_password, row[1])
                ):
                    raise InvalidCredentials("当前密码错误")

                updated_username = (
                    username_update[0] if username_update else row[0]
                )
                updated_username_key = (
                    username_update[1]
                    if username_update
                    else updated_username.casefold()
                )
                updated_password_hash = (
                    hash_password(new_password)
                    if new_password
                    else row[1]
                )
                connection.execute(
                    """
                    UPDATE app.users
                    SET username = %s,
                        username_key = %s,
                        password_hash = %s,
                        password_changed_at = CASE
                            WHEN %s THEN %s
                            ELSE password_changed_at
                        END,
                        updated_at = %s
                    WHERE id = %s
                    """,
                    (
                        updated_username,
                        updated_username_key,
                        updated_password_hash,
                        bool(new_password),
                        now,
                        now,
                        user_id,
                    ),
                )
                connection.execute(
                    "DELETE FROM app.sessions WHERE user_id = %s",
                    (user_id,),
                )
                return self._create_session(
                    connection,
                    AuthUser(id=user_id, username=updated_username),
                    normalize_ip(ip_address),
                    user_agent,
                    now,
                )
        except errors.UniqueViolation as exc:
            raise DuplicateUsername("用户名已存在") from exc

    def cleanup(self) -> None:
        with self._connect() as connection:
            connection.execute(
                "DELETE FROM app.sessions WHERE expires_at <= now()"
            )

    def _create_session(
        self,
        connection: psycopg.Connection[Any],
        user: AuthUser,
        ip_address: str,
        user_agent: str,
        now: datetime,
    ) -> AuthSession:
        raw_token = secrets.token_urlsafe(48)
        expires_at = now + SESSION_TTL
        connection.execute(
            """
            INSERT INTO app.sessions (
                token_hash, user_id, expires_at, ip_address, user_agent
            )
            VALUES (%s, %s, %s, %s, %s)
            """,
            (
                token_hash(raw_token),
                user.id,
                expires_at,
                normalize_ip(ip_address),
                user_agent[:500],
            ),
        )
        return AuthSession(
            user=user,
            raw_token=raw_token,
            expires_at=expires_at,
        )
