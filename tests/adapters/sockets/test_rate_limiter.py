"""Tests für `RateLimiter` (Story S-005).

Covers (dateneingang): AC3

`app.adapters.sockets.base.RateLimiter` kapselt den Mindestabstand
zwischen zwei Abrufen derselben Adapter-Instanz (AC3 — Rate-Limits sind je
Quelle im Adapter gekapselt). Zeit-/Sleep-Funktionen werden hier durch
Fakes ersetzt, damit die Tests deterministisch und ohne echte Wartezeit
laufen.
"""

from __future__ import annotations

import asyncio

import pytest

from app.adapters.sockets.base import RateLimiter


class _FakeSleep:
    """Zeichnet Sleep-Aufrufe auf, statt tatsächlich zu warten."""

    def __init__(self) -> None:
        self.calls: list[float] = []

    async def __call__(self, seconds: float) -> None:
        self.calls.append(seconds)


class _FakeClock:
    def __init__(self, start: float) -> None:
        self._now = start

    def __call__(self) -> float:
        return self._now

    def advance(self, delta: float) -> None:
        self._now += delta


def test_first_call_never_waits() -> None:
    """@trace dateneingang#AC3 — der erste Abruf einer Adapter-Instanz
    wartet nie, da noch kein Vorgänger-Aufruf existiert."""
    clock = _FakeClock(100.0)
    sleep = _FakeSleep()
    limiter = RateLimiter(2.0, sleep=sleep, monotonic=clock)

    asyncio.run(limiter.wait())

    assert sleep.calls == []


def test_second_call_within_min_interval_waits_remaining_time() -> None:
    """@trace dateneingang#AC3 — ein zweiter Abruf innerhalb des
    Mindestabstands wartet exakt die verbleibende Zeit, statt das
    Rate-Limit der Quelle zu überschreiten."""
    clock = _FakeClock(100.0)
    sleep = _FakeSleep()
    limiter = RateLimiter(2.0, sleep=sleep, monotonic=clock)

    asyncio.run(limiter.wait())
    clock.advance(0.5)
    asyncio.run(limiter.wait())

    assert sleep.calls == pytest.approx([1.5])


def test_call_after_min_interval_elapsed_does_not_wait() -> None:
    """@trace dateneingang#AC3 — verstreicht der Mindestabstand von selbst
    (z. B. weil der Aufrufer ohnehin langsamer ist), wird nicht zusätzlich
    gewartet."""
    clock = _FakeClock(100.0)
    sleep = _FakeSleep()
    limiter = RateLimiter(2.0, sleep=sleep, monotonic=clock)

    asyncio.run(limiter.wait())
    clock.advance(5.0)
    asyncio.run(limiter.wait())

    assert sleep.calls == []


def test_rejects_negative_min_interval() -> None:
    """@trace dateneingang#AC3 — ein negativer Mindestabstand ist eine
    Fehlkonfiguration und wird beim Erzeugen abgelehnt."""
    with pytest.raises(ValueError):
        RateLimiter(-1.0)
