from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent

load_dotenv(BASE_DIR / ".env")

BOT_EDITION: str = os.getenv("BOT_EDITION", "default").strip().lower()
IS_TURKISH_BOT: bool = BOT_EDITION == "tr"
BOT_TOKEN: str = os.getenv("BOT_TOKEN_TR" if IS_TURKISH_BOT else "BOT_TOKEN", "").strip()
ADMIN_TG_ID: int = int(
    os.getenv("ADMIN_TG_ID_TR" if IS_TURKISH_BOT else "ADMIN_TG_ID", "0").strip()
    or "0"
)
OWNER_PASSWORD_HASH: str = os.getenv(
    "OWNER_PASSWORD_HASH_TR" if IS_TURKISH_BOT else "OWNER_PASSWORD_HASH", ""
).strip()
DB_PATH: Path = BASE_DIR / os.getenv(
    "DB_PATH_TR" if IS_TURKISH_BOT else "DB_PATH",
    "db/bot_tr.sqlite3" if IS_TURKISH_BOT else "db/bot.sqlite3",
)

TEMPLATES_DIR: Path = BASE_DIR / "templates"
ASSETS_DIR: Path = BASE_DIR / "renderer" / "assets"
FONTS_DIR: Path = BASE_DIR / "renderer" / "assets" / "fonts"
OUTPUT_DIR: Path = BASE_DIR / "output"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
ASSETS_DIR.mkdir(parents=True, exist_ok=True)
FONTS_DIR.mkdir(parents=True, exist_ok=True)
DB_PATH.parent.mkdir(parents=True, exist_ok=True)


def validate() -> None:
    if not BOT_TOKEN:
        token_name = "BOT_TOKEN_TR" if IS_TURKISH_BOT else "BOT_TOKEN"
        raise RuntimeError(f"{token_name} не задан в .env")
    if not ADMIN_TG_ID:
        admin_name = "ADMIN_TG_ID_TR" if IS_TURKISH_BOT else "ADMIN_TG_ID"
        raise RuntimeError(f"{admin_name} не задан в .env")
