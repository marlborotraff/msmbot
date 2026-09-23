from __future__ import annotations

import re

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message

import config
from db.queries import (
    User,
    add_user,
    grant_owner,
    owner_password_wait_seconds,
    record_failed_owner_password,
    use_invite,
)
from handlers.menu import send_main_menu

router = Router(name="auth")

_START_RE = re.compile(r"/start(?:@\w+)?(?:\s+(.*))?$", re.IGNORECASE)
_password_hasher = PasswordHasher()


class OwnerClaim(StatesGroup):
    waiting_password = State()


def _invite_code_from_start(message: Message) -> str | None:
    text = (message.text or "").strip()
    m = _START_RE.match(text)
    if not m:
        return None
    arg = (m.group(1) or "").strip()
    if not arg:
        return None
    return arg.upper()


@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext, user: User | None = None) -> None:
    await state.clear()
    if user is not None:
        if user.status == "blocked":
            await message.answer("Доступ закрыт.")
            return
        await send_main_menu(message, user)
        return

    code = _invite_code_from_start(message)
    if code is None:
        await message.answer("Для входа владельца отправьте /owner. Для доступа администратора нужен инвайт.")
        return

    invite = await use_invite(code, telegram_id=message.from_user.id)
    if invite is None:
        await message.answer("Код неверный или уже использован.")
        return

    user = await add_user(
        telegram_id=message.from_user.id,
        username=message.from_user.username,
        role=invite.role,
        created_by=invite.created_by,
    )
    await message.answer(
        "✅ Доступ выдан. Вы администратор.\n"
        "Новых администраторов по инвайту добавляет владелец бота."
    )
    await send_main_menu(message, user)


@router.message(Command("owner"))
async def start_owner_claim(message: Message, state: FSMContext, user: User | None = None) -> None:
    if message.chat.type != "private":
        await message.answer("Пароль владельца вводите только в личном чате с ботом.")
        return
    if user is not None and user.role == "owner" and user.status == "active":
        await message.answer("У вас уже есть права владельца.")
        return
    if not config.OWNER_PASSWORD_HASH:
        await message.answer("Вход по паролю пока не настроен.")
        return
    wait_seconds = await owner_password_wait_seconds(message.from_user.id)
    if wait_seconds:
        await message.answer(f"Слишком много попыток. Повторите через {max(1, (wait_seconds + 59) // 60)} мин.")
        return
    await state.set_state(OwnerClaim.waiting_password)
    await message.answer("Отправьте пароль владельца следующим сообщением. После проверки я удалю сообщение с паролем.")


@router.message(OwnerClaim.waiting_password, F.text)
async def receive_owner_password(message: Message, state: FSMContext) -> None:
    if message.chat.type != "private":
        await state.clear()
        return
    password = message.text or ""
    deleted = True
    try:
        await message.delete()
    except (TelegramBadRequest, TelegramForbiddenError):
        deleted = False
    await state.clear()
    if not deleted:
        await message.answer("Не удалось удалить сообщение с паролем. Удалите его вручную в чате.")
    wait_seconds = await owner_password_wait_seconds(message.from_user.id)
    if wait_seconds:
        await message.answer(f"Слишком много попыток. Повторите через {max(1, (wait_seconds + 59) // 60)} мин.")
        return
    try:
        matched = _password_hasher.verify(config.OWNER_PASSWORD_HASH, password)
    except VerifyMismatchError:
        matched = False
    except (InvalidHashError, VerificationError):
        await message.answer("Проверка пароля сейчас недоступна. Сообщите владельцу бота.")
        return
    if not matched:
        wait_seconds = await record_failed_owner_password(message.from_user.id)
        if wait_seconds:
            await message.answer("Неверный пароль. Попытки временно ограничены на 15 минут.")
        else:
            await message.answer("Неверный пароль. Для повторной попытки отправьте /owner.")
        return
    user = await grant_owner(message.from_user.id, message.from_user.username)
    await message.answer("Права владельца выданы вашему аккаунту.")
    await send_main_menu(message, user)
