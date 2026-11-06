"""Notification's process: `python -m app.worker`. It has no HTTP API; it consumes
notification.events until SIGTERM or SIGINT, and prunes the processed_events inbox about
hourly in a background thread."""

import logging
import threading

from app.config import get_settings
from app.consumer import consumer
from app.db import SessionLocal
from app.handlers import run_inbox_pruner
from app.platform.lifespan import run_until_signalled
from app.platform.logging import configure_logging

log = logging.getLogger("sgjio.notification")


def main() -> None:
    configure_logging()
    log.info("notification worker starting (email backend: %s)", get_settings().email_backend)
    stop_pruner = threading.Event()
    pruner = threading.Thread(
        target=run_inbox_pruner,
        args=(SessionLocal, stop_pruner),
        name="notification-inbox-pruner",
        daemon=True,
    )
    pruner.start()
    try:
        run_until_signalled(SessionLocal, consumers=[consumer])
    finally:
        stop_pruner.set()
        pruner.join(timeout=10)
    log.info("notification worker stopped")


if __name__ == "__main__":
    main()
