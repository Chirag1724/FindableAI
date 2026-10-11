"""CLI entrypoint: ``python -m app.worker``."""

from __future__ import annotations

import asyncio
import logging
import sys

from app.core.config import settings
from app.jobs.worker import ScanJobWorker, install_signal_handlers


def _configure_logging() -> None:
    level = getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO)
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
        stream=sys.stdout,
    )


async def _amain() -> None:
    _configure_logging()
    worker = ScanJobWorker()
    install_signal_handlers(worker)
    await worker.run_forever()


def main() -> None:
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
    asyncio.run(_amain())


if __name__ == "__main__":
    main()
