from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import os
from typing import Mapping, Optional, Protocol, Union


FIXED_NOW_ENV = "MEMWIZ_FIXED_NOW"


class Clock(Protocol):
    def now(self) -> datetime:
        ...


@dataclass(frozen=True)
class UtcClock:
    def now(self) -> datetime:
        return datetime.now(timezone.utc)


@dataclass(frozen=True)
class FixedClock:
    moment: datetime

    def __post_init__(self) -> None:
        normalized = _coerce_datetime(self.moment)
        object.__setattr__(self, "moment", normalized)

    @classmethod
    def from_value(cls, value: Union[str, datetime]) -> "FixedClock":
        return cls(_coerce_datetime(value))

    def now(self) -> datetime:
        return self.moment


@dataclass
class CommandClock:
    clock: Clock = field(default_factory=UtcClock)
    _timestamp: Optional[str] = None

    def timestamp(self) -> str:
        if self._timestamp is None:
            self._timestamp = now_timestamp(self.clock)

        return self._timestamp


def build_command_clock(env: Optional[Mapping[str, str]] = None) -> CommandClock:
    environment = env if env is not None else os.environ
    fixed_now = environment.get(FIXED_NOW_ENV)

    if fixed_now:
        return CommandClock(FixedClock.from_value(fixed_now))

    return CommandClock()


def now_timestamp(clock: Optional[Clock] = None) -> str:
    active_clock = clock if clock is not None else UtcClock()
    return format_timestamp(active_clock.now())


def format_timestamp(moment: datetime) -> str:
    return _coerce_datetime(moment).isoformat().replace("+00:00", "Z")


def _coerce_datetime(value: Union[str, datetime]) -> datetime:
    if isinstance(value, str):
        candidate = value.strip()

        if candidate.endswith("Z"):
            candidate = f"{candidate[:-1]}+00:00"

        parsed = datetime.fromisoformat(candidate)
    else:
        parsed = value

    if parsed.tzinfo is None:
        raise ValueError("clock values must include timezone information")

    return parsed.astimezone(timezone.utc).replace(microsecond=0)
