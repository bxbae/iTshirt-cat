"""One place to ask for "now", so rules and tests can pin the time."""
from datetime import datetime, timezone

_override: datetime | None = None


def now() -> datetime:
    return _override or datetime.now(timezone.utc)


def freeze(at: datetime | None) -> None:
    global _override
    _override = at
