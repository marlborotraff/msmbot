from __future__ import annotations

import secrets
import string
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional

from db.database import get_db


@dataclass
class User:
    id: int
    telegram_id: int
    username: Optional[str]
    role: str
    status: str
    created_by: Optional[int]
    created_at: str


@dataclass
class Invite:
    id: int
    code: str
    role: str
    created_by: int
    used_by: Optional[int]
    created_at: str
    used_at: Optional[str]


def _row_to_user(row) -> Optional[User]:
    if row is None:
        return None
    return User(
        id=row["id"],
        telegram_id=row["telegram_id"],
        username=row["username"],
        role=row["role"],
        status=row["status"],
        created_by=row["created_by"],
        created_at=row["created_at"],
    )


def _row_to_invite(row) -> Optional[Invite]:
    if row is None:
        return None
    return Invite(
        id=row["id"],
        code=row["code"],
        role=row["role"],
        created_by=row["created_by"],
        used_by=row["used_by"],
        created_at=row["created_at"],
        used_at=row["used_at"],
    )


async def get_user(telegram_id: int) -> Optional[User]:
    async with get_db() as db:
        cur = await db.execute(
            "SELECT * FROM users WHERE telegram_id = ?",
            (telegram_id,),
        )
        row = await cur.fetchone()
        return _row_to_user(row)


async def add_user(
    telegram_id: int,
    username: Optional[str],
    role: str,
    created_by: Optional[int],
) -> User:
    async with get_db() as db:
        await db.execute(
            """
            INSERT INTO users(telegram_id, username, role, status, created_by, created_at)
            VALUES (?, ?, ?, 'active', ?, ?)
            """,
            (telegram_id, username, role, created_by, datetime.utcnow().isoformat(timespec="seconds")),
        )
        await db.commit()
    user = await get_user(telegram_id)
    assert user is not None
    return user


async def update_user_status(telegram_id: int, status: str) -> None:
    async with get_db() as db:
        await db.execute(
            "UPDATE users SET status = ? WHERE telegram_id = ?",
            (status, telegram_id),
        )
        await db.commit()


async def delete_user(telegram_id: int) -> None:
    async with get_db() as db:
        await db.execute("DELETE FROM users WHERE telegram_id = ?", (telegram_id,))
        await db.commit()


async def list_users(created_by: Optional[int] = None) -> list[User]:
    sql = "SELECT * FROM users"
    params: tuple = ()
    if created_by is not None:
        sql += " WHERE created_by = ?"
        params = (created_by,)
    sql += " ORDER BY id ASC"
    async with get_db() as db:
        cur = await db.execute(sql, params)
        rows = await cur.fetchall()
        return [u for u in (_row_to_user(r) for r in rows) if u is not None]


async def owner_password_wait_seconds(telegram_id: int) -> int:
    async with get_db() as db:
        cur = await db.execute(
            "SELECT locked_until FROM owner_password_attempts WHERE telegram_id = ?",
            (telegram_id,),
        )
        row = await cur.fetchone()
    if row is None or not row["locked_until"]:
        return 0
    remaining = datetime.fromisoformat(row["locked_until"]) - datetime.now(timezone.utc)
    return max(0, int(remaining.total_seconds()) + 1)


async def record_failed_owner_password(telegram_id: int) -> int:
    now = datetime.now(timezone.utc)
    async with get_db() as db:
        await db.execute("BEGIN IMMEDIATE")
        cur = await db.execute(
            "SELECT failed_count, locked_until FROM owner_password_attempts WHERE telegram_id = ?",
            (telegram_id,),
        )
        row = await cur.fetchone()
        if row and row["locked_until"]:
            remaining = datetime.fromisoformat(row["locked_until"]) - now
            if remaining.total_seconds() > 0:
                return int(remaining.total_seconds()) + 1
        failures = (int(row["failed_count"]) if row and not row["locked_until"] else 0) + 1
        locked_until = (now + timedelta(minutes=15)).isoformat() if failures >= 5 else None
        await db.execute(
            """
            INSERT INTO owner_password_attempts(telegram_id, failed_count, locked_until)
            VALUES (?, ?, ?)
            ON CONFLICT(telegram_id) DO UPDATE SET
                failed_count = excluded.failed_count,
                locked_until = excluded.locked_until
            """,
            (telegram_id, failures, locked_until),
        )
        await db.commit()
    return 15 * 60 if locked_until else 0


async def grant_owner(telegram_id: int, username: Optional[str]) -> User:
    async with get_db() as db:
        await db.execute("BEGIN IMMEDIATE")
        await db.execute(
            """
            INSERT INTO users(telegram_id, username, role, status, created_by, created_at)
            VALUES (?, ?, 'owner', 'active', NULL, ?)
            ON CONFLICT(telegram_id) DO UPDATE SET
                role = 'owner', username = excluded.username
            WHERE users.status = 'active'
            """,
            (telegram_id, username, datetime.now(timezone.utc).isoformat(timespec="seconds")),
        )
        await db.execute(
            "DELETE FROM owner_password_attempts WHERE telegram_id = ?", (telegram_id,)
        )
        await db.commit()
    user = await get_user(telegram_id)
    if user is None or user.role != "owner" or user.status != "active":
        raise ValueError("Не удалось выдать права владельца")
    return user


def _gen_code(length: int = 10) -> str:
    alphabet = string.ascii_uppercase + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(length))


async def create_invite(role: str, created_by: int) -> Invite:
    code = _gen_code()
    async with get_db() as db:
        await db.execute(
            """
            INSERT INTO invite_codes(code, role, created_by, created_at)
            VALUES (?, ?, ?, ?)
            """,
            (code, role, created_by, datetime.utcnow().isoformat(timespec="seconds")),
        )
        await db.commit()
        cur = await db.execute("SELECT * FROM invite_codes WHERE code = ?", (code,))
        row = await cur.fetchone()
        inv = _row_to_invite(row)
        assert inv is not None
        return inv


async def get_invite(code: str) -> Optional[Invite]:
    async with get_db() as db:
        cur = await db.execute("SELECT * FROM invite_codes WHERE code = ?", (code,))
        row = await cur.fetchone()
        return _row_to_invite(row)


async def use_invite(code: str, telegram_id: int) -> Optional[Invite]:
    norm = code.strip().upper()
    now = datetime.utcnow().isoformat(timespec="seconds")
    async with get_db() as db:
        cur = await db.execute(
            """
            UPDATE invite_codes
            SET used_by = ?, used_at = ?
            WHERE code = ? AND used_by IS NULL
            """,
            (telegram_id, now, norm),
        )
        await db.commit()
        if cur.rowcount == 0:
            return None
        cur = await db.execute("SELECT * FROM invite_codes WHERE code = ?", (norm,))
        row = await cur.fetchone()
        return _row_to_invite(row)


async def list_invites(created_by: Optional[int] = None, unused_only: bool = False) -> list[Invite]:
    sql = "SELECT * FROM invite_codes WHERE 1=1"
    params: list = []
    if created_by is not None:
        sql += " AND created_by = ?"
        params.append(created_by)
    if unused_only:
        sql += " AND used_by IS NULL"
    sql += " ORDER BY id DESC"
    async with get_db() as db:
        cur = await db.execute(sql, tuple(params))
        rows = await cur.fetchall()
        return [i for i in (_row_to_invite(r) for r in rows) if i is not None]
