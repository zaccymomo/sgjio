"""Wiring a service together: middleware, error handlers, health, background threads.

    from contextlib import asynccontextmanager
    from app.platform.lifespan import background_workers, install_platform

    @asynccontextmanager
    async def lifespan(app):
        with background_workers(SessionLocal, relay=True, consumers=[consumer]):
            yield

    app = FastAPI(lifespan=lifespan)
    install_platform(app, SessionLocal)

RUN_RELAY and RUN_CONSUMER (default true) switch the threads off, e.g. in tests. A worker
with no HTTP API (Notification) calls `run_until_signalled(...)` from `python -m app.worker`.
"""

import logging
import signal
import threading
from collections.abc import Callable, Iterator, Sequence
from contextlib import contextmanager

from fastapi import FastAPI
from sqlalchemy.orm import Session

from .config import get_config
from .consumer import Consumer
from .errors import install_error_handlers
from .health import health_router
from .logging import CorrelationIdMiddleware
from .outbox import run_relay

log = logging.getLogger("sgjio.workers")


def install_platform(app: FastAPI, session_factory: Callable[[], Session]) -> None:
    app.add_middleware(CorrelationIdMiddleware)
    install_error_handlers(app)
    app.include_router(health_router(session_factory))


@contextmanager
def background_workers(
    session_factory: Callable[[], Session],
    *,
    relay: bool = False,
    consumers: Sequence[Consumer] = (),
    stop: threading.Event | None = None,
) -> Iterator[threading.Event]:
    """Run the outbox relay and/or consumers in daemon threads for the duration of the block."""
    config = get_config()
    stop = stop or threading.Event()
    threads = []
    if relay and config.run_relay:
        threads.append(
            threading.Thread(
                target=run_relay,
                args=(session_factory, stop),
                name=f"{config.service_name}-relay",
                daemon=True,
            )
        )
    if config.run_consumer:
        for consumer in consumers:
            threads.append(
                threading.Thread(
                    target=consumer.run,
                    args=(stop,),
                    name=f"{consumer.queue}-consumer",
                    daemon=True,
                )
            )
    for thread in threads:
        thread.start()
    log.info("background workers started: %s", [thread.name for thread in threads] or "none")
    try:
        yield stop
    finally:
        stop.set()
        for thread in threads:
            thread.join(timeout=10)


def run_until_signalled(
    session_factory: Callable[[], Session],
    *,
    relay: bool = False,
    consumers: Sequence[Consumer] = (),
) -> None:
    """Block until SIGTERM or SIGINT, running the workers meanwhile."""
    stop = threading.Event()
    for sig in (signal.SIGTERM, signal.SIGINT):
        signal.signal(sig, lambda *_: stop.set())
    with background_workers(session_factory, relay=relay, consumers=consumers, stop=stop):
        while not stop.wait(1):
            pass
