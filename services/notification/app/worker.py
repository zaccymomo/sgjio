"""STUB (step 0): idles until stopped. The notification builder replaces it with the real
consumer (python -m app.worker)."""

import logging
import signal
import threading

logging.basicConfig(level=logging.INFO)
stop = threading.Event()


def main() -> None:
    for sig in (signal.SIGTERM, signal.SIGINT):
        signal.signal(sig, lambda *_: stop.set())
    logging.getLogger("notification").info("notification stub worker running")
    while not stop.wait(60):
        pass


if __name__ == "__main__":
    main()
