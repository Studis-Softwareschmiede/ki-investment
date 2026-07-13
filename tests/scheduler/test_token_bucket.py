"""Tests für `TokenBucket` (Story S-020).

Covers (dateneingang): AC11

`app.scheduler.token_bucket.TokenBucket` drosselt Abrufe je Quelle statt
das Rate-Limit zu überschreiten (AC11, Edge-Case "Rate-Limit-Verletzung
droht → Token-Bucket drosselt"). Zeit-/Sleep-Funktionen sind wie bei
`app.adapters.sockets.base.RateLimiter` durch Fakes ersetzt, damit die
Tests deterministisch und ohne echte Wartezeit laufen.
"""

from __future__ import annotations

import asyncio

import pytest

from app.scheduler.token_bucket import TokenBucket


class _FakeClock:
    def __init__(self, start: float) -> None:
        self._now = start

    def __call__(self) -> float:
        return self._now

    def advance(self, delta: float) -> None:
        self._now += delta


class _FakeSleep:
    """An die `_FakeClock` gekoppelt: ein simuliertes Warten von `seconds`
    lässt die Zeit tatsächlich um `seconds` weiterlaufen — sonst würde
    `TokenBucket.acquire()`s Warteschleife nie terminieren (der Bucket
    füllt nach echter verstrichener Zeit nach, nicht nach Anzahl
    `sleep()`-Aufrufen)."""

    def __init__(self, clock: _FakeClock) -> None:
        self._clock = clock
        self.calls: list[float] = []

    async def __call__(self, seconds: float) -> None:
        self.calls.append(seconds)
        self._clock.advance(seconds)


def test_bucket_starts_full_and_first_acquires_never_wait() -> None:
    """@trace dateneingang#AC11 — der Bucket startet mit voller
    Burst-Kapazität; die ersten `capacity` Abrufe warten nicht."""
    clock = _FakeClock(0.0)
    sleep = _FakeSleep(clock)
    bucket = TokenBucket(capacity=3, refill_rate_pro_sekunde=1.0, sleep=sleep, monotonic=clock)

    asyncio.run(_acquire_n(bucket, 3))

    assert sleep.calls == []


def test_bucket_throttles_once_capacity_is_exhausted() -> None:
    """@trace dateneingang#AC11 — ist die Burst-Kapazität aufgebraucht,
    wartet der nächste Abruf auf ein nachgefülltes Token (drosselt statt
    das Rate-Limit zu überschreiten)."""
    clock = _FakeClock(0.0)
    sleep = _FakeSleep(clock)
    bucket = TokenBucket(capacity=1, refill_rate_pro_sekunde=2.0, sleep=sleep, monotonic=clock)

    asyncio.run(bucket.acquire())  # verbraucht das einzige Start-Token

    async def _naechster() -> None:
        await bucket.acquire()

    asyncio.run(_naechster())

    assert sleep.calls == pytest.approx([0.5])  # 1 fehlendes Token / 2 Tokens/s


def test_bucket_refills_over_time_up_to_capacity() -> None:
    """@trace dateneingang#AC11 — zwischen zwei Abrufen verstrichene Zeit
    füllt den Bucket nach (gedeckelt auf `capacity`), sodass ein Abruf
    nach ausreichender Wartezeit ohne erneutes Warten möglich ist."""
    clock = _FakeClock(0.0)
    sleep = _FakeSleep(clock)
    bucket = TokenBucket(capacity=2, refill_rate_pro_sekunde=1.0, sleep=sleep, monotonic=clock)

    asyncio.run(_acquire_n(bucket, 2))  # Bucket jetzt leer
    clock.advance(5.0)  # deutlich mehr als genug zum Nachfüllen auf capacity=2

    asyncio.run(_acquire_n(bucket, 2))

    assert sleep.calls == []
    assert bucket.verfuegbare_tokens == pytest.approx(0.0)


def test_rejects_non_positive_capacity_or_refill_rate() -> None:
    """@trace dateneingang#AC11 — eine Fehlkonfiguration (Kapazität < 1
    oder Nachfüllrate <= 0) wird beim Erzeugen abgelehnt."""
    with pytest.raises(ValueError):
        TokenBucket(capacity=0, refill_rate_pro_sekunde=1.0)
    with pytest.raises(ValueError):
        TokenBucket(capacity=1, refill_rate_pro_sekunde=0.0)


async def _acquire_n(bucket: TokenBucket, n: int) -> None:
    for _ in range(n):
        await bucket.acquire()
