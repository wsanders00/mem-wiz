from __future__ import annotations

from datetime import datetime, timedelta, timezone

from memwiz.clock import CommandClock, Clock, FixedClock, now_timestamp


def test_now_timestamp_uses_utc_z_suffix(make_fixed_clock) -> None:
    clock = make_fixed_clock("2026-04-08T10:30:00-05:00")

    assert now_timestamp(clock) == "2026-04-08T15:30:00Z"


def test_fixed_clock_is_deterministic(make_fixed_clock) -> None:
    clock = make_fixed_clock("2026-04-08T15:30:00Z")

    assert clock.now() == datetime(2026, 4, 8, 15, 30, tzinfo=timezone.utc)
    assert clock.now() == datetime(2026, 4, 8, 15, 30, tzinfo=timezone.utc)


def test_command_clock_reuses_one_timestamp_across_multiple_fields() -> None:
    clock = CommandClock(IncrementingClock())

    assert clock.timestamp() == "2026-04-08T15:30:00Z"
    assert clock.timestamp() == "2026-04-08T15:30:00Z"


class IncrementingClock(Clock):
    def __init__(self) -> None:
        self.current = datetime(2026, 4, 8, 15, 30, tzinfo=timezone.utc)

    def now(self) -> datetime:
        value = self.current
        self.current = self.current + timedelta(seconds=1)
        return value
