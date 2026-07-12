"""FRED-Adapter — konkrete Referenzimplementierung von `SocketAdapter` (AC1).

FRED (Federal Reserve Economic Data, St. Louis Fed) ist eine der
kostenlosen MVP-Quellen (`docs/specs/dateneingang.md`, Main Success
Scenario Schritt 2 + A2, NFR-Kostendisziplin). Die volle Quellen-Registry
mit allen 12 Quellen und ihrer Anlageklassen-Zuordnung (AC5) sowie das
Revisions-Re-Pull-Verhalten (AC12, A2) sind Nicht-Ziel dieser Story
(S-006/Folge-Stories) — dieser Adapter zeigt nur die Adapter-Abstraktion
(AC1) konkret: Auth per API-Key aus Env-Var + Log-Maskierung (AC3), ein
gekapseltes Rate-Limit (AC3) und Normalisierung auf den einheitlichen
`Datenpunkt` (AC1/AC2).
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlencode
from urllib.request import urlopen

from app.adapters.sockets.base import RateLimiter, SocketAdapter
from app.core.secrets import mask_secret

logger = logging.getLogger(__name__)

#: Env-Var für den FRED-API-Key (AC3 — nie hartkodiert, nie im Klartext geloggt).
FRED_API_KEY_ENV_VAR = "FRED_API_KEY"
_BASE_URL = "https://api.stlouisfed.org/fred/series/observations"
# Konservativer Default-Mindestabstand zwischen zwei FRED-Abrufen dieser
# Adapter-Instanz (AC3) — kein recherchierter/verbindlicher FRED-Vertragswert,
# per Konstruktor überschreibbar. Das volle Token-Bucket-Rate-Limiting über
# mehrere Worker (AC11) ist NICHT Teil dieser Story.
_DEFAULT_MIN_INTERVAL_SECONDS = 1.0


class FredConfigError(RuntimeError):
    """`FredAdapter` wurde ohne gültigen API-Key instanziiert (AC3)."""


class FredAdapter(SocketAdapter):
    """Adapter für die FRED-`series/observations`-REST-API.

    Auth: API-Key aus Env-Var `FRED_API_KEY` (AC3). Welche `series_id`
    welchem Anlageklassen-Tag zugeordnet ist, liegt hier fix am
    Konstruktor — die vollständige Quellen→Anlageklassen-Registry (AC5) ist
    Gegenstand von S-006, nicht dieser Story.
    """

    quelle_name = "fred"

    def __init__(
        self,
        *,
        series_id: str,
        anlageklassen_tag: int,
        api_key: str | None = None,
        http_get: Callable[[str], bytes] | None = None,
        rate_limiter: RateLimiter | None = None,
    ) -> None:
        resolved_key = api_key if api_key is not None else os.environ.get(FRED_API_KEY_ENV_VAR)
        if not resolved_key:
            raise FredConfigError(
                f"Kein FRED-API-Key konfiguriert — erwartet Env-Var {FRED_API_KEY_ENV_VAR}."
            )
        super().__init__(rate_limiter=rate_limiter or RateLimiter(_DEFAULT_MIN_INTERVAL_SECONDS))
        self._series_id = series_id
        self._anlageklassen_tag = anlageklassen_tag
        self._api_key = resolved_key
        self._http_get = http_get or self._default_http_get
        logger.debug(
            "FredAdapter für Serie %s initialisiert (api_key=%s)",
            series_id,
            mask_secret(resolved_key),
        )

    @staticmethod
    def _default_http_get(url: str) -> bytes:
        with urlopen(url, timeout=10) as response:
            return response.read()

    async def _fetch_raw(self) -> dict[str, Any]:
        query = urlencode(
            {"series_id": self._series_id, "api_key": self._api_key, "file_type": "json"}
        )
        url = f"{_BASE_URL}?{query}"
        rohbytes = await asyncio.to_thread(self._http_get, url)
        return json.loads(rohbytes)

    def _normalize(self, rohantwort: dict[str, Any]) -> list[dict[str, Any]]:
        kandidaten: list[dict[str, Any]] = []
        for beobachtung in rohantwort.get("observations", []):
            datum = beobachtung.get("date")
            timestamp: datetime | None = None
            if datum:
                try:
                    timestamp = datetime.strptime(datum, "%Y-%m-%d").replace(tzinfo=UTC)
                except ValueError:
                    timestamp = None
            wert = beobachtung.get("value")
            # FRED markiert fehlende Beobachtungen mit ".": ohne belastbaren
            # Wert gibt es keinen sinnvollen Qualitätsindikator (AC2) — der
            # Kandidat wird in `fetch()` verworfen statt geschätzt.
            qualitaetsindikator = "roh" if wert not in (None, ".") else None
            kandidaten.append(
                {
                    "wert": wert,
                    "quelle": self.quelle_name,
                    "timestamp": timestamp,
                    "anlageklassen_tag": self._anlageklassen_tag,
                    "qualitaetsindikator": qualitaetsindikator,
                }
            )
        return kandidaten
