"""Socket-Adapter-Port (Modul 1, architecture.md §4 `app/adapters/sockets/`).

Jede registrierte Datenquelle bekommt genau einen Adapter, der von
`SocketAdapter` erbt (AC1, `docs/specs/dateneingang.md`). Ein Konsument
(später `orchestration/ingest_pipeline.py`, S-006ff.) ruft ausschliesslich
`fetch()` auf und erhält eine Liste normalisierter `Datenpunkt`-Instanzen —
quellen-unabhängig identisch strukturiert, egal welche konkrete Unterklasse
dahintersteckt (AC1).

`fetch()` kapselt:
- **Rate-Limit** (AC3) — ein einfacher Mindestabstand je Adapter-Instanz
  (`RateLimiter`). Die volle Queue-/Token-Bucket-Orchestrierung über mehrere
  Worker (AC11, `app/scheduler/`) ist NICHT Teil dieser Story.
- **Metadaten-Vollständigkeit** (AC2) — Kandidaten, die `Datenpunkt` nicht
  validieren (fehlende Pflicht-Metadaten oder `anlageklassen_tag`
  ausserhalb 1..11), werden hier verworfen, nie an den Aufrufer gereicht.

Auth (API-Keys/OAuth, AC3) ist Sache der konkreten Unterklasse (z. B.
`app.adapters.sockets.fred.FredAdapter`) — dort wird auch die
Credential-Herkunft (Env-Var) und Log-Maskierung (`app.core.secrets
.mask_secret`) umgesetzt.

I/O-lastige Ingest-Arbeit ist laut ADR-004 (architecture.md §8) async —
`fetch()`/`_fetch_raw()` sind daher Koroutinen; die parallele Orchestrierung
mehrerer Adapter über `asyncio.TaskGroup` ist Sache der Orchestration-Schicht
(späterer Story-Scope), nicht dieser Basisklasse.
"""

from __future__ import annotations

import asyncio
import logging
import time
from abc import ABC, abstractmethod
from collections.abc import Awaitable, Callable
from typing import Any

from pydantic import ValidationError

from app.contracts.dateneingang import Datenpunkt

logger = logging.getLogger(__name__)


class RateLimiter:
    """Erzwingt einen Mindestabstand zwischen zwei Abrufen derselben
    Adapter-Instanz (AC3). Zeit-/Sleep-Funktionen sind injizierbar, damit
    Tests ohne echte Wartezeit laufen."""

    def __init__(
        self,
        min_interval_seconds: float,
        *,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        if min_interval_seconds < 0:
            raise ValueError("min_interval_seconds darf nicht negativ sein.")
        self._min_interval = min_interval_seconds
        self._sleep = sleep
        self._monotonic = monotonic
        self._last_call: float | None = None

    async def wait(self) -> None:
        """Wartet (falls nötig), bis der Mindestabstand seit dem letzten
        Aufruf erreicht ist, und merkt sich den aktuellen Aufrufzeitpunkt."""
        now = self._monotonic()
        if self._last_call is not None:
            remaining = self._min_interval - (now - self._last_call)
            if remaining > 0:
                await self._sleep(remaining)
        self._last_call = self._monotonic()


class SocketAdapter(ABC):
    """Adapter-Port: eine Unterklasse je registrierter Datenquelle (AC1)."""

    #: Name der Quelle, wie er im Pflicht-Metadatum `quelle` erscheint (AC2).
    quelle_name: str

    def __init__(self, *, rate_limiter: RateLimiter | None = None) -> None:
        self._rate_limiter = rate_limiter

    async def fetch(self) -> list[Datenpunkt]:
        """Ruft die Quelle rate-limit-gekapselt ab (AC3) und liefert
        ausschliesslich gültige, einheitlich strukturierte Datenpunkte
        (AC1, AC2)."""
        if self._rate_limiter is not None:
            await self._rate_limiter.wait()
        rohantwort = await self._fetch_raw()
        datenpunkte: list[Datenpunkt] = []
        for kandidat in self._normalize(rohantwort):
            try:
                datenpunkte.append(Datenpunkt(**kandidat))
            except ValidationError as exc:
                logger.warning(
                    "Datenpunkt von Quelle %s verworfen (Pflicht-Metadaten "
                    "unvollständig/ungültig, AC2): %s",
                    self.quelle_name,
                    exc,
                )
        return datenpunkte

    @abstractmethod
    async def _fetch_raw(self) -> Any:
        """Authentifiziert sich und ruft die Quelle ab; liefert die
        quellenspezifische Rohantwort (AC3)."""

    @abstractmethod
    def _normalize(self, rohantwort: Any) -> list[dict[str, Any]]:
        """Übersetzt die Rohantwort in Kandidaten-Dicts für `Datenpunkt`
        (AC1) — Feldnamen: `wert`, `quelle`, `timestamp`,
        `anlageklassen_tag`, `qualitaetsindikator`. Fehlende/ungültige Werte
        führen in `fetch()` zum Verwerfen des Kandidaten (AC2), nicht zu
        einer Schätzung hier."""
