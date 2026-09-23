from __future__ import annotations

import asyncio
import logging
import re
import time
from pathlib import Path

logger = logging.getLogger(__name__)

MAX_AGE_SECONDS = 24 * 60 * 60
CHECK_INTERVAL_SECONDS = 60 * 60
GENERATED_IMAGE_NAME = re.compile(r"[a-z][a-z0-9]*_[0-9a-f]{32}\.png")


def remove_old_images(output_dir: Path) -> None:
    cutoff = time.time() - MAX_AGE_SECONDS
    try:
        for path in output_dir.iterdir():
            if not GENERATED_IMAGE_NAME.fullmatch(path.name) or path.is_symlink():
                continue
            try:
                if path.is_file() and path.stat().st_mtime < cutoff:
                    path.unlink()
                    logger.info("Удалено старое изображение: %s", path.name)
            except OSError:
                logger.exception("Не удалось проверить или удалить изображение: %s", path)
    except OSError:
        logger.exception("Не удалось просмотреть папку с результатами: %s", output_dir)


async def cleanup_loop(output_dir: Path) -> None:
    while True:
        await asyncio.to_thread(remove_old_images, output_dir)
        await asyncio.sleep(CHECK_INTERVAL_SECONDS)
