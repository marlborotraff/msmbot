from __future__ import annotations

from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, TelegramObject

import config
from db.queries import add_user, get_user


class AccessMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        tg_user = None
        if isinstance(event, Message):
            tg_user = event.from_user
        elif isinstance(event, CallbackQuery):
            tg_user = event.from_user

        if tg_user is None:
            return await handler(event, data)

        if tg_user.id == config.ADMIN_TG_ID:
            user = await get_user(tg_user.id)
            if user is None:
                user = await add_user(
                    telegram_id=tg_user.id,
                    username=tg_user.username,
                    role="owner",
                    created_by=None,
                )
            data["user"] = user
            return await handler(event, data)

        user = await get_user(tg_user.id)
        data["user"] = user

        text = (event.text or "").strip().lower() if isinstance(event, Message) else ""
        is_start = text.startswith("/start")
        is_owner_command = text.startswith("/owner")
        is_owner_password = data.get("raw_state") == "OwnerClaim:waiting_password"

        if user is None:
            if is_start or is_owner_command or is_owner_password:
                return await handler(event, data)
            if isinstance(event, Message):
                return None
            elif isinstance(event, CallbackQuery):
                await event.answer("Нет доступа.", show_alert=True)
            return None

        if user.status == "blocked":
            if isinstance(event, Message):
                await event.answer("Доступ закрыт.")
            elif isinstance(event, CallbackQuery):
                await event.answer("Доступ закрыт.", show_alert=True)
            return None

        return await handler(event, data)
