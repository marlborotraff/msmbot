from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Callable

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup, default_state
from aiogram.types import (
    CallbackQuery,
    FSInputFile,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

from db.queries import User
from handlers.menu import (
    MAIN_MENU_REPLY_TO_DOC,
    REPLY_BTN_ADMIN,
    main_menu_kb,
    send_main_menu,
)
from renderer.html_renderer import HtmlRenderer
from renderer.new_docs_renderer import (
    uz_words,
)

logger = logging.getLogger(__name__)
router = Router(name="generate")
html_renderer = HtmlRenderer()


async def start_html_renderer() -> None:
    await html_renderer.start()


async def stop_html_renderer() -> None:
    await html_renderer.stop()


def validate_text(value: str) -> str:
    v = value.strip()
    if not v:
        raise ValueError("заполните это поле")
    if len(v) > 200:
        raise ValueError("не более 200 символов")
    return v


def validate_date(value: str) -> str:
    v = value.strip()
    try:
        dt = datetime.strptime(v, "%d.%m.%Y")
    except ValueError as e:
        raise ValueError("укажите дату в формате ДД.ММ.ГГГГ, например 08.05.2026") from e
    return dt.strftime("%d.%m.%Y")


def validate_amount(value: str) -> int:
    v = re.sub(r"[\s,_]", "", value.strip())
    if not v.isdigit():
        raise ValueError("укажите сумму цифрами, например 5 200 000")
    n = int(v)
    if n <= 0 or n > 9_999_999_999:
        raise ValueError("укажите сумму от 1 до 9 999 999 999")
    return n


def fmt_amount(n: int) -> str:
    return f"{n:,}".replace(",", " ")


@dataclass
class Field:
    key: str
    label: str
    example: str
    validator: Callable[[str], Any]


DOC_TITLES = {
    "frame13": "РД6 AML",
    "humo": "RD 7 HUMO",
    "conversion": "RD 4 Конвертация",
    "moliyaviy": "РД 5 ОФФШОРНЫЙ СБОР",
}

DOC_FILENAMES = {
    "frame13": "РД6 AML",
    "humo": "RD 7 HUMO",
    "conversion": "RD 4 Конвертация",
    "moliyaviy": "РД 5 ОФФШОРНЫЙ СБОР",
}


def _download_filename(doc: str, path: Path) -> str:
    base = DOC_FILENAMES.get(doc, "document")
    return f"{base}{path.suffix}"

DOC_FIELDS: dict[str, list[Field]] = {
    "frame13": [
        Field("amount", "Сумма в Jarayon parametrlari", "5200000", validate_amount),
    ],
    "humo": [
        Field("date", "Дата", "27.07.2026", validate_date),
        Field("full_name", "ФИО", "Иванов Иван Иванович", validate_text),
        Field("account_id", "ID аккаунта лида", "12345", validate_text),
        Field("amount", "Сумма", "1350000", validate_amount),
    ],
    "conversion": [
        Field("date", "Дата", "27.07.2026", validate_date),
        Field("limit_amount", "Сумма лимита вывода", "10000000", validate_amount),
        Field("fee_amount", "Сумма комиссии конвертации", "1531288", validate_amount),
    ],
    "moliyaviy": [
        Field("amount", "Сумма", "3149000", validate_amount),
    ],
}


class GenState(StatesGroup):
    waiting_list = State()


def _instructions(doc: str) -> str:
    fields = DOC_FIELDS[doc]
    lines = [
        f"<b>{DOC_TITLES[doc]}</b>",
        "",
        "Отправьте одним сообщением все поля списком — каждое поле с новой строки.",
        "Можно с номерами или без них:",
        "",
    ]
    for i, f in enumerate(fields, 1):
        lines.append(f"<b>{i}.</b> {f.label}")
    lines.append("")
    lines.append("<b>Пример:</b>")
    lines.append("<pre>" + "\n".join(f"{i}. {f.example}" for i, f in enumerate(fields, 1)) + "</pre>")
    return "\n".join(lines)


def _cancel_kb() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="✖ Отмена", callback_data="g:cancel")]]
    )


async def _begin_gen_message(message: Message, state: FSMContext, doc: str) -> None:
    await state.set_state(GenState.waiting_list)
    await state.update_data(doc=doc)
    await message.answer(_instructions(doc), reply_markup=_cancel_kb())


def _strip_list_prefix(line: str) -> str:
    s = line.strip()
    m = re.match(r"^\d{1,3}\s*\)\s*(.+)$", s)
    if m:
        return m.group(1).strip()
    m = re.match(r"^\d{1,3}\.(?!\d)\s*(.+)$", s)
    if m:
        return m.group(1).strip()
    m = re.match(r"^\d{1,3}\s*[-–]\s+(.+)$", s)
    if m:
        return m.group(1).strip()
    m = re.match(r"^\d{1,3}:\s+(.+)$", s)
    if m:
        return m.group(1).strip()
    return s


def plural_fields(count: int) -> str:
    if count % 10 == 1 and count % 100 != 11:
        return "поле"
    if count % 10 in (2, 3, 4) and count % 100 not in (12, 13, 14):
        return "поля"
    return "полей"


def _parse_lines(text: str, expected: int) -> list[str]:
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    cleaned = [_strip_list_prefix(ln).strip() for ln in lines]
    if len(cleaned) < expected:
        raise ValueError(f"Нужно заполнить {expected} {plural_fields(expected)}, а получено {len(cleaned)}.")
    return cleaned[:expected]


def _validate_all(doc: str, raw_values: list[str]) -> tuple[dict[str, Any], list[str]]:
    fields = DOC_FIELDS[doc]
    data: dict[str, Any] = {}
    errors: list[str] = []
    for i, (field, raw) in enumerate(zip(fields, raw_values), 1):
        try:
            data[field.key] = field.validator(raw)
        except ValueError as e:
            errors.append(f"• <b>{field.label}</b>: {e}.")
    return data, errors


@router.callback_query(F.data.startswith("gen:"))
async def start_gen(cb: CallbackQuery, state: FSMContext) -> None:
    doc = cb.data.split(":")[1]
    if doc not in DOC_FIELDS:
        await cb.answer("Этот документ сейчас недоступен.", show_alert=True)
        return
    await state.set_state(GenState.waiting_list)
    await state.update_data(doc=doc)
    try:
        await cb.message.edit_text(_instructions(doc), reply_markup=_cancel_kb())
    except TelegramBadRequest:
        await cb.message.answer(_instructions(doc), reply_markup=_cancel_kb())
    await cb.answer()


@router.message(StateFilter(default_state), F.text.in_(set(MAIN_MENU_REPLY_TO_DOC)))
async def reply_menu_pick_doc(message: Message, state: FSMContext, user: User) -> None:
    doc = MAIN_MENU_REPLY_TO_DOC[message.text.strip()]
    await _begin_gen_message(message, state, doc)


@router.message(StateFilter(default_state), F.text == REPLY_BTN_ADMIN)
async def reply_menu_admin(message: Message, user: User) -> None:
    from handlers.admin import admin_kb, _is_env_owner

    if not _is_env_owner(user):
        await message.answer("Админ-панель недоступна.")
        return
    await message.answer("🛠 Админ-панель", reply_markup=admin_kb(user))


@router.callback_query(F.data == "g:cancel", GenState.waiting_list)
async def cancel_gen(cb: CallbackQuery, state: FSMContext, user: User) -> None:
    await state.clear()
    try:
        await cb.message.edit_text("Отменено.")
    except TelegramBadRequest:
        pass
    await send_main_menu(cb.message, user)
    await cb.answer()


@router.message(GenState.waiting_list, F.text)
async def receive_list(
    message: Message,
    state: FSMContext,
    user: User,
) -> None:
    data_st = await state.get_data()
    doc = data_st["doc"]
    fields = DOC_FIELDS[doc]

    try:
        raw_values = _parse_lines(message.text or "", expected=len(fields))
    except ValueError as e:
        await message.answer(
            f"❌ {e}\n\n{_instructions(doc)}", reply_markup=_cancel_kb()
        )
        return

    collected, errors = _validate_all(doc, raw_values)
    if errors:
        await message.answer(
            "❌ Проверьте данные:\n\n" + "\n".join(errors) + "\n\nИсправьте и отправьте весь список ещё раз.",
            reply_markup=_cancel_kb(),
        )
        return

    status_msg = await message.answer("⏳ Готовлю документ…")

    try:
        png_path = await _render_doc(doc, collected, html_renderer)
    except Exception:
        logger.exception("Ошибка генерации %s", doc)
        try:
            await status_msg.edit_text("❌ Не удалось подготовить документ. Попробуйте ещё раз через минуту.")
        except TelegramBadRequest:
            await message.answer("❌ Не удалось подготовить документ. Попробуйте ещё раз через минуту.")
        await state.clear()
        await send_main_menu(message, user)
        return

    kb = main_menu_kb(user)
    try:
        sent = await message.answer_document(
            document=FSInputFile(str(png_path), filename=_download_filename(doc, png_path)),
            caption=DOC_TITLES[doc],
            parse_mode=None,
        )
        try:
            await sent.edit_reply_markup(reply_markup=kb)
        except TelegramBadRequest as e:
            logger.warning("Не удалось прикрепить меню к документу: %s", e)
            await message.answer("Главное меню:", reply_markup=kb)
    finally:
        try:
            Path(png_path).unlink(missing_ok=True)
        except Exception:
            pass
        try:
            await status_msg.delete()
        except TelegramBadRequest:
            pass

    await state.clear()


async def _render_doc(doc: str, data: dict[str, Any], renderer: HtmlRenderer) -> Path:
    if doc == "frame13":
        amount = data["amount"]
        return await renderer.render(
            "frame13.html",
            {"amount": f"{fmt_amount(amount)} so’m"},
            kind="frame13",
        )

    if doc == "humo":
        return await renderer.render(
            "humo.html",
            {
                "date": data["date"],
                "full_name": data["full_name"],
                "account_id": data["account_id"],
                "amount": f"{fmt_amount(data['amount'])} ({uz_words(data['amount'])}) so'm",
            },
            kind="humo",
        )

    if doc == "conversion":
        ctx = {
            "date": data["date"],
            "limit_amount": fmt_amount(data["limit_amount"]),
            "fee_amount": fmt_amount(data["fee_amount"]),
        }
        return await renderer.render("ph_conversion.html", ctx, kind="conversion")

    if doc == "moliyaviy":
        amount = data["amount"]
        return await renderer.render(
            "moliyaviy.html",
            {
                "amount_only": fmt_amount(amount),
            },
            kind="moliyaviy",
        )

    raise ValueError(f"Unknown doc: {doc}")
