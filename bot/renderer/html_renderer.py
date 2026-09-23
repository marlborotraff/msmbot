from __future__ import annotations

import asyncio
import logging
import random
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import uuid4

from jinja2 import Environment, FileSystemLoader, select_autoescape
from playwright.async_api import Browser, async_playwright

import config

logger = logging.getLogger(__name__)

VIEWPORTS = {
    "ph1": {"width": 820, "height": 1180},
    "ph2": {"width": 1320, "height": 800},
    "ph3": {"width": 400, "height": 920},
    "ph4": {"width": 800, "height": 1100},
    "ph5": {"width": 794, "height": 1123},
    "ph6": {"width": 390, "height": 844},
    "ph9": {"width": 1240, "height": 1754},
    "conversion": {"width": 900, "height": 1273},
    "humo": {"width": 820, "height": 1160},
    "frame13": {"width": 2483, "height": 3512},
    "moliyaviy": {"width": 1240, "height": 1754},
}


class HtmlRenderer:
    def __init__(self) -> None:
        self._pw = None
        self._browser: Browser | None = None
        self._env = Environment(
            loader=FileSystemLoader(str(config.TEMPLATES_DIR)),
            autoescape=select_autoescape(["html", "xml"]),
        )
        self._env.filters["asset_svg"] = self._asset_svg_filter
        self._env.filters["asset_data_uri"] = self._asset_data_uri_filter
        self._lock = asyncio.Lock()

    @staticmethod
    def _asset_svg_filter(filename: str) -> str:
        p = config.ASSETS_DIR / filename
        if not p.exists():
            return ""
        return p.read_text(encoding="utf-8")

    @staticmethod
    def _asset_data_uri_filter(filename: str) -> str:
        import base64
        import mimetypes

        p = config.ASSETS_DIR / filename
        if not p.exists():
            return ""
        mime, _ = mimetypes.guess_type(str(p))
        if mime is None:
            if p.suffix.lower() == ".svg":
                mime = "image/svg+xml"
            else:
                mime = "application/octet-stream"
        b64 = base64.b64encode(p.read_bytes()).decode("ascii")
        return f"data:{mime};base64,{b64}"

    async def start(self) -> None:
        self._pw = await async_playwright().start()
        self._browser = await self._pw.chromium.launch(headless=True)

    async def stop(self) -> None:
        if self._browser:
            await self._browser.close()
        if self._pw:
            await self._pw.stop()

    async def render(self, template_name: str, data: dict[str, Any], kind: str) -> Path:
        if self._browser is None:
            raise RuntimeError("HtmlRenderer не инициализирован")

        tmpl = self._env.get_template(template_name)
        rel_assets = (config.ASSETS_DIR.resolve()).as_posix()
        html = tmpl.render(**data, assets_dir=f"file:///{rel_assets}")

        viewport = VIEWPORTS.get(kind, {"width": 800, "height": 1100})
        uid = uuid4().hex
        tmp_html = config.OUTPUT_DIR / f"{kind}_{uid}.html"
        out_path = config.OUTPUT_DIR / f"{kind}_{uid}.png"
        tmp_html.write_text(html, encoding="utf-8")

        async with self._lock:
            context = await self._browser.new_context(
                viewport=viewport,
                device_scale_factor=1 if kind == "frame13" else 2,
                offline=kind == "ph6",
            )
            page = await context.new_page()
            try:
                file_url = tmp_html.resolve().as_uri()
                await page.goto(file_url, wait_until="networkidle")
                element = await page.query_selector("#doc")
                if element is None:
                    await page.screenshot(path=str(out_path), full_page=True)
                else:
                    await element.screenshot(path=str(out_path))
            finally:
                await context.close()
                try:
                    tmp_html.unlink(missing_ok=True)
                except Exception:
                    pass

        logger.info("Сгенерирован %s -> %s", template_name, out_path)
        return out_path

    async def render_pdf(self, template_name: str, data: dict[str, Any], kind: str) -> Path:
        if self._browser is None:
            raise RuntimeError("HtmlRenderer не инициализирован")

        tmpl = self._env.get_template(template_name)
        rel_assets = (config.ASSETS_DIR.resolve()).as_posix()
        html = tmpl.render(**data, assets_dir=f"file:///{rel_assets}")

        viewport = VIEWPORTS.get(kind, {"width": 794, "height": 1123})
        uid = uuid4().hex
        tmp_html = config.OUTPUT_DIR / f"{kind}_{uid}.html"
        out_path = config.OUTPUT_DIR / f"{kind}_{uid}.pdf"
        tmp_html.write_text(html, encoding="utf-8")

        async with self._lock:
            context = await self._browser.new_context(viewport=viewport)
            page = await context.new_page()
            try:
                file_url = "file:///" + tmp_html.resolve().as_posix()
                await page.goto(file_url, wait_until="networkidle")
                await page.emulate_media(media="print")
                await page.pdf(
                    path=str(out_path),
                    format="A4",
                    print_background=True,
                    margin={"top": "0", "right": "0", "bottom": "0", "left": "0"},
                )
            finally:
                await context.close()
                try:
                    tmp_html.unlink(missing_ok=True)
                except Exception:
                    pass

        logger.info("Сгенерирован PDF %s -> %s", template_name, out_path)
        return out_path


def build_ph2_rows(first: dict[str, Any], locale: str = "ru") -> dict[str, Any]:
    base_dt: datetime = first["datetime"]
    base_id: int = first["row_id"]

    sample_names = (
        [
            "Emre Yıldız",
            "Zeynep Şahin",
            "Mustafa Çelik",
            "Elif Aydın",
            "Burak Arslan",
            "Selin Koç",
            "Mert Özdemir",
        ]
        if locale == "tr"
        else [
            "Жускенова Кадиша Ергазиевна",
            "Майленов Жангельды Бертаевич",
            "Батырбеков Нурлан Азаматович",
            "Сарсенов Айдар Канатович",
            "Турекулов Ерлан Бекетович",
            "Аманжолова Динара Сериковна",
            "Ермаганбетов Серик Жангирович",
        ]
    )
    rnd = random.Random(first.get("seed") or int(base_dt.timestamp()))
    names = rnd.sample(sample_names, 3)

    rows = [first]
    cur_dt = base_dt
    cur_id = base_id
    for i in range(3):
        cur_dt = cur_dt - timedelta(minutes=rnd.randint(1, 3))
        cur_id -= 1
        if locale == "tr":
            iban = "TR" + "".join(str(rnd.randint(0, 9)) for _ in range(24))
            card = " ".join(iban[j : j + 4] for j in range(0, len(iban), 4))
        else:
            card = "{} {} {} {}".format(
                rnd.choice(["4400", "5336", "4000", "5469", "4154"]),
                rnd.randint(1000, 9999),
                rnd.randint(100, 9999),
                rnd.randint(1000, 9999),
            )
        amount = rnd.randint(150_000, 600_000)
        rows.append(
            {
                "row_id": cur_id,
                "datetime": cur_dt,
                "type": "Para çekme" if locale == "tr" else "Вывод",
                "card": card,
                "name": names[i],
                "status": "ok",
                "amount": amount,
            }
        )
    return {"rows": rows}
