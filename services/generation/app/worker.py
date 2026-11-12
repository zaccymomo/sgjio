"""Generation's process: `python -m app.worker`. It has no HTTP API; it consumes
generation.events and relays its outbox until SIGTERM or SIGINT."""

import logging

from app.config import get_settings
from app.consumer import consumer
from app.db import SessionLocal
from app.llm import build_llm
from app.platform.lifespan import run_until_signalled
from app.platform.logging import configure_logging

log = logging.getLogger("sgjio.generation")


def main() -> None:
    configure_logging()
    settings = get_settings()
    log.info(
        "generation worker starting (enabled: %s, model: %s)",
        settings.generation_enabled,
        "fake" if settings.generation_fake else settings.generation_model or "(none)",
    )
    build_llm(settings)  # warns now if the real model is chosen but not configured
    run_until_signalled(SessionLocal, relay=True, consumers=[consumer])
    log.info("generation worker stopped")


if __name__ == "__main__":
    main()
