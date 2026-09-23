from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncIterator

import aiosqlite

import config

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    telegram_id INTEGER UNIQUE NOT NULL,
    username TEXT,
    role TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'active',
    created_by INTEGER,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS invite_codes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    code TEXT UNIQUE NOT NULL,
    role TEXT NOT NULL,
    created_by INTEGER NOT NULL,
    used_by INTEGER,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    used_at TEXT
);

CREATE TABLE IF NOT EXISTS owner_password_attempts (
    telegram_id INTEGER PRIMARY KEY,
    failed_count INTEGER NOT NULL DEFAULT 0,
    locked_until TEXT
);

CREATE INDEX IF NOT EXISTS idx_users_tg ON users(telegram_id);
CREATE INDEX IF NOT EXISTS idx_invite_code ON invite_codes(code);
"""


async def init_db() -> None:
    async with aiosqlite.connect(config.DB_PATH) as db:
        await db.executescript(SCHEMA)
        await db.execute(
            "UPDATE users SET role = 'owner' WHERE telegram_id = ?",
            (config.ADMIN_TG_ID,),
        )
        await db.execute("UPDATE users SET role = 'admin' WHERE role = 'subadmin'")
        await db.commit()


@asynccontextmanager
async def get_db() -> AsyncIterator[aiosqlite.Connection]:
    async with aiosqlite.connect(config.DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        yield db
