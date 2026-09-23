from __future__ import annotations

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

from db.queries import (
    User,
    create_invite,
    delete_user,
    get_user,
    list_invites,
    list_users,
    update_user_status,
)

router = Router(name="admin")

INVITE_ADMIN_ROLE = "admin"


def _is_env_owner(user: User | None) -> bool:
    return user is not None and user.role == "owner" and user.status == "active"


def _can_use_admin_panel(user: User | None) -> bool:
    return user is not None and user.role in ("owner", "admin") and user.status == "active"


def admin_kb(user: User) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    if _is_env_owner(user):
        rows.append(
            [
                InlineKeyboardButton(
                    text="➕ Одноразовый инвайт (новый админ)",
                    callback_data="adm:invite",
                )
            ]
        )
        rows.append([InlineKeyboardButton(text="🎟 Инвайты", callback_data="adm:invites")])
        rows.append([InlineKeyboardButton(text="👥 Администраторы", callback_data="adm:admins")])
    rows.append([InlineKeyboardButton(text="« Закрыть", callback_data="adm:close")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


@router.message(Command("admin"))
async def cmd_admin(message: Message, user: User) -> None:
    if not _can_use_admin_panel(user):
        await message.answer("Команда недоступна.")
        return
    hint = ""
    if not _is_env_owner(user):
        hint = "\n\nИнвайты для новых админов создаёт владелец бота."
    await message.answer("🛠 Админ-панель" + hint, reply_markup=admin_kb(user))


@router.callback_query(F.data == "admin:open")
async def open_admin(cb: CallbackQuery, user: User) -> None:
    if not _can_use_admin_panel(user):
        await cb.answer("Недоступно.", show_alert=True)
        return
    hint = ""
    if not _is_env_owner(user):
        hint = "\n\nИнвайты для новых админов создаёт владелец бота."
    await cb.message.edit_text("🛠 Админ-панель" + hint, reply_markup=admin_kb(user))
    await cb.answer()


@router.callback_query(F.data == "adm:close")
async def close_admin(cb: CallbackQuery) -> None:
    await cb.message.edit_text("Закрыто.")
    await cb.answer()


@router.callback_query(F.data == "adm:invite")
async def make_invite(cb: CallbackQuery, user: User) -> None:
    if not _is_env_owner(user):
        await cb.answer("Только владелец бота может создавать инвайты.", show_alert=True)
        return

    invite = await create_invite(
        role=INVITE_ADMIN_ROLE,
        created_by=user.telegram_id,
    )
    await cb.message.answer(
        "🎟 Одноразовый инвайт создан\n"
        f"Код: <code>{invite.code}</code>\n\n"
        "Новый админ должен написать боту (одним сообщением):\n"
        f"<code>/start {invite.code}</code>\n\n"
        "Или открыть бота по ссылке с параметром start (код в ссылке — тот же)."
    )
    await cb.answer("Готово")


@router.callback_query(F.data == "adm:invites")
async def show_invites(cb: CallbackQuery, user: User) -> None:
    if not _is_env_owner(user):
        await cb.answer("Только владелец бота может смотреть список инвайтов.", show_alert=True)
        return
    invites = await list_invites(created_by=None)
    if not invites:
        await cb.message.answer("Инвайтов нет.")
        await cb.answer()
        return

    lines = []
    for inv in invites[:50]:
        status = "✅ использован" if inv.used_by else "🆓 свободен"
        lines.append(f"<code>{inv.code}</code> · {status}")
    await cb.message.answer("🎟 Инвайты:\n" + "\n".join(lines))
    await cb.answer()


@router.callback_query(F.data == "adm:admins")
async def show_admins(cb: CallbackQuery, user: User) -> None:
    if not _is_env_owner(user):
        await cb.answer("Недоступно.", show_alert=True)
        return

    users = await list_users()
    users = [u for u in users if u.telegram_id != user.telegram_id]
    if not users:
        await cb.message.answer("Других администраторов нет.")
        await cb.answer()
        return

    for u in users[:30]:
        flag = "🟢" if u.status == "active" else "🔴"
        username = f"@{u.username}" if u.username else "—"
        text = (
            f"{flag} <b>{username}</b>\n"
            f"ID: <code>{u.telegram_id}</code>\n"
            f"Роль: {u.role}\n"
            f"Статус: {u.status}"
        )
        action = "ban" if u.status == "active" else "unban"
        label = "🚫 Заблокировать" if action == "ban" else "✅ Разблокировать"
        kb_rows = [] if u.role == "owner" else [
            [InlineKeyboardButton(text=label, callback_data=f"adm:{action}:{u.telegram_id}")],
            [InlineKeyboardButton(text="🗑 Удалить из бота", callback_data=f"adm:del:{u.telegram_id}")],
        ]
        kb = InlineKeyboardMarkup(inline_keyboard=kb_rows)
        await cb.message.answer(text, reply_markup=kb)
    await cb.answer()


@router.callback_query(F.data.startswith("adm:del:"))
async def remove_admin(cb: CallbackQuery, user: User) -> None:
    if not _is_env_owner(user):
        await cb.answer("Недоступно.", show_alert=True)
        return
    target_id = int(cb.data.split(":")[2])
    target = await get_user(target_id)
    if target is not None and target.role == "owner":
        await cb.answer("Нельзя.", show_alert=True)
        return
    await delete_user(target_id)
    await cb.answer("Удалён")
    await cb.message.edit_text(cb.message.html_text + "\n\n→ <b>удалён из бота</b>")


@router.callback_query(F.data.startswith("adm:ban:") | F.data.startswith("adm:unban:"))
async def toggle_ban(cb: CallbackQuery, user: User) -> None:
    if not _is_env_owner(user):
        await cb.answer("Только владелец бота может менять блокировки.", show_alert=True)
        return
    parts = cb.data.split(":")
    action = parts[1]
    target_id = int(parts[2])

    target = await get_user(target_id)
    if target is not None and target.role == "owner":
        await cb.answer("Владельца блокировать нельзя.", show_alert=True)
        return

    new_status = "blocked" if action == "ban" else "active"
    await update_user_status(target_id, new_status)
    await cb.answer("Готово")
    await cb.message.edit_text(
        cb.message.html_text + f"\n\n→ статус обновлён: <b>{new_status}</b>"
    )
