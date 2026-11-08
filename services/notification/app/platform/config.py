"""The few settings the plumbing needs, read from the environment.

A service whose own Settings class reads them from a .env file calls `configure(...)`
at start-up so both agree.
"""

import os
from dataclasses import dataclass, replace


def _flag(name: str, default: bool) -> bool:
    return os.environ.get(name, str(default)).strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class PlatformConfig:
    service_name: str
    gateway_key: str
    broker_url: str
    run_relay: bool
    run_consumer: bool


def from_env() -> PlatformConfig:
    return PlatformConfig(
        service_name=os.environ.get("SERVICE_NAME", "unknown"),
        gateway_key=os.environ.get("GATEWAY_KEY", ""),
        broker_url=os.environ.get("BROKER_URL", "amqp://sgjio:sgjio@localhost:5672/%2F"),
        run_relay=_flag("RUN_RELAY", True),
        run_consumer=_flag("RUN_CONSUMER", True),
    )


config = from_env()


def configure(**changes) -> PlatformConfig:
    """Override settings, e.g. configure(service_name="content", gateway_key=settings.x)."""
    global config
    config = replace(config, **changes)
    return config


def get_config() -> PlatformConfig:
    return config
