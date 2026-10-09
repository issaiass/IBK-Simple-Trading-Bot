"""US Eastern time helpers."""
from datetime import datetime, time
from zoneinfo import ZoneInfo

ET = ZoneInfo("America/New_York")


def now_et() -> datetime:
    return datetime.now(ET)


def parse_hhmm(value: str) -> time:
    hour, minute = value.split(":")
    return time(int(hour), int(minute))


def stamp(message: str, now: datetime) -> str:
    """Prefix a message with [HH:MM:SS ET]."""
    return f"[{now:%H:%M:%S} ET] {message}"
