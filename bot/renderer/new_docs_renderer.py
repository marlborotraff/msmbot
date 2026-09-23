from __future__ import annotations


_UZ_UNITS = ("", "bir", "ikki", "uch", "to'rt", "besh", "olti", "yetti", "sakkiz", "to'qqiz")
_UZ_TENS = ("", "o'n", "yigirma", "o'ttiz", "qirq", "ellik", "oltmish", "yetmish", "sakson", "to'qson")


def _uz_under_thousand(number: int) -> str:
    parts: list[str] = []
    hundreds, rest = divmod(number, 100)
    tens, units = divmod(rest, 10)
    if hundreds:
        parts.extend([_UZ_UNITS[hundreds], "yuz"])
    if tens:
        parts.append(_UZ_TENS[tens])
    if units:
        parts.append(_UZ_UNITS[units])
    return " ".join(parts)


def uz_words(number: int) -> str:
    if number == 0:
        return "nol"

    parts: list[str] = []
    billions, remainder = divmod(number, 1_000_000_000)
    millions, remainder = divmod(remainder, 1_000_000)
    thousands, rest = divmod(remainder, 1_000)

    if billions:
        parts.extend([_uz_under_thousand(billions), "milliard"])
    if millions:
        parts.extend([_uz_under_thousand(millions), "million"])
    if thousands:
        parts.extend([_uz_under_thousand(thousands), "ming"])
    if rest:
        parts.append(_uz_under_thousand(rest))
    return " ".join(parts)
