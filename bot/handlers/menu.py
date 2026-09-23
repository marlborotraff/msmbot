from __future__ import annotations

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    Message,
    ReplyKeyboardMarkup,
)

from db.queries import User

router = Router(name="menu")

REPLY_BTN_FRAME13 = "РД6 AML"
REPLY_BTN_HUMO = "RD 7 HUMO"
REPLY_BTN_CONVERSION = "RD 4 Конвертация"
REPLY_BTN_MOLIYAVIY = "РД 5 ОФФШОРНЫЙ СБОР"
REPLY_BTN_ADMIN = "🛠 Админ"

MAIN_MENU_REPLY_TO_DOC: dict[str, str] = {
    REPLY_BTN_CONVERSION: "conversion",
    REPLY_BTN_MOLIYAVIY: "moliyaviy",
    REPLY_BTN_FRAME13: "frame13",
    REPLY_BTN_HUMO: "humo",
}


def main_menu_kb(user: User) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text=REPLY_BTN_CONVERSION, callback_data="gen:conversion")],
        [InlineKeyboardButton(text=REPLY_BTN_MOLIYAVIY, callback_data="gen:moliyaviy")],
        [InlineKeyboardButton(text=REPLY_BTN_FRAME13, callback_data="gen:frame13")],
        [InlineKeyboardButton(text=REPLY_BTN_HUMO, callback_data="gen:humo")],
    ]
    if user.role == "owner":
        rows.append([InlineKeyboardButton(text="🛠 Админ-панель", callback_data="admin:open")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def main_menu_reply_kb(user: User) -> ReplyKeyboardMarkup:
    rows = [
        [KeyboardButton(text=REPLY_BTN_CONVERSION), KeyboardButton(text=REPLY_BTN_MOLIYAVIY)],
        [KeyboardButton(text=REPLY_BTN_FRAME13), KeyboardButton(text=REPLY_BTN_HUMO)],
    ]
    if user.role == "owner":
        rows.append([KeyboardButton(text=REPLY_BTN_ADMIN)])
    return ReplyKeyboardMarkup(
        keyboard=rows,
        resize_keyboard=True,
        is_persistent=True,
        input_field_placeholder="Выберите тип отрисовки…",
    )


async def send_main_menu(message: Message, user: User) -> None:
    await message.answer(
        "Главное меню. Выберите документ (кнопки снизу или сообщение «Меню»):",
        reply_markup=main_menu_reply_kb(user),
    )


@router.message(F.text.casefold() == "меню")
async def cmd_menu(message: Message, state: FSMContext, user: User) -> None:
    await state.clear()
    await send_main_menu(message, user)
