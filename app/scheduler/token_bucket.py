"""Token-Bucket je Quelle (AC11, `docs/specs/dateneingang.md`): "Worker mit
einem Token-Bucket je Quelle ... sodass die quellenspezifischen
Rate-Limits eingehalten und die unterschiedlichen Frequenzen entkoppelt
werden." Edge-Case der Spec: "Rate-Limit-Verletzung droht → Token-Bucket
drosselt statt zu überschreiten."

Ein `TokenBucket` gehört genau EINER Quelle (`app.scheduler.worker.Worker`
instanziiert je aktiver Quelle einen eigenen) — das entkoppelt
unterschiedliche Quellen-Frequenzen strukturell voneinander: eine
gedrosselte Quelle blockiert keine andere (AC10-Edge-Case "ohne andere
Quellen zu blockieren"; dieselbe Entkopplung gilt analog für AC11).

Zeit-/Sleep-Funktionen sind injizierbar (analog
`app.adapters.sockets.base.RateLimiter`), damit Tests deterministisch und
ohne echte Wartezeit laufen.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable


class TokenBucket:
    """Klassischer Token-Bucket: `capacity` Tokens Burst-Kapazität, füllt
    sich mit `refill_rate_pro_sekunde` Tokens/Sekunde bis maximal
    `capacity` nach. `acquire()` wartet (falls nötig), bis mindestens ein
    Token verfügbar ist, und verbraucht es dann (AC11)."""

    def __init__(
        self,
        *,
        capacity: int,
        refill_rate_pro_sekunde: float,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        if capacity < 1:
            raise ValueError("capacity muss mindestens 1 sein.")
        if refill_rate_pro_sekunde <= 0:
            raise ValueError("refill_rate_pro_sekunde muss positiv sein.")
        self._capacity = capacity
        self._refill_rate = refill_rate_pro_sekunde
        self._sleep = sleep
        self._monotonic = monotonic
        self._tokens = float(capacity)
        self._last_refill = monotonic()

    def _fuelle_nach(self) -> None:
        now = self._monotonic()
        vergangen = now - self._last_refill
        if vergangen > 0:
            self._tokens = min(self._capacity, self._tokens + vergangen * self._refill_rate)
            self._last_refill = now

    async def acquire(self) -> None:
        """Wartet, bis mindestens ein Token verfügbar ist, und verbraucht
        es dann (AC11 — drosselt statt das Rate-Limit zu überschreiten)."""
        while True:
            self._fuelle_nach()
            if self._tokens >= 1:
                self._tokens -= 1
                return
            fehlend = 1 - self._tokens
            wartezeit = fehlend / self._refill_rate
            await self._sleep(wartezeit)

    @property
    def verfuegbare_tokens(self) -> float:
        """Inspektion (z. B. Tests) — löst vor dem Lesen ein Nachfüllen aus."""
        self._fuelle_nach()
        return self._tokens


__all__ = ["TokenBucket"]
