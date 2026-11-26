"""Settings, read from the environment once at start-up."""
import os
from dataclasses import dataclass

DEFAULT_API_URL = "http://10.100.102.12/api"
DEFAULT_TIMEOUT_SECONDS = 40.0


@dataclass(frozen=True)
class Settings:
    api_url: str
    timeout_seconds: float


def load_settings() -> Settings:
    # A trailing slash would double up when a path is appended.
    api_url = os.environ.get("BRISA_API_URL", DEFAULT_API_URL).rstrip("/")
    raw = os.environ.get("BRISA_TIMEOUT_SECONDS", "")
    try:
        timeout = float(raw) if raw else DEFAULT_TIMEOUT_SECONDS
    except ValueError:
        raise SystemExit(f"BRISA_TIMEOUT_SECONDS must be a number, got {raw!r}") from None
    if timeout <= 0:
        raise SystemExit(f"BRISA_TIMEOUT_SECONDS must be positive, got {raw!r}")
    return Settings(api_url=api_url, timeout_seconds=timeout)
