"""Tests für den FRED-Adapter (Story S-005, konkrete Referenzimplementierung
von `SocketAdapter`).

Covers (dateneingang): AC1, AC2, AC3

`app.adapters.sockets.fred.FredAdapter` ist die erste konkrete
Quellen-Implementierung des Adapter-Ports (AC1). Diese Tests decken: Auth
per API-Key aus Env-Var, ohne Key keine Instanziierung (AC3); der Key
erscheint nie im Klartext in Logs, nur maskiert (AC3,
`app.core.secrets.mask_secret`); FRED-typische fehlende Beobachtungen
(`"."`) werden mangels Qualitätsindikator verworfen, nicht geschätzt
(AC2); die normalisierten Datenpunkte tragen alle vier Pflicht-Metadaten
(AC1/AC2); das Rate-Limit ist im Adapter gekapselt (AC3).
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import UTC, datetime

import pytest

from app.adapters.sockets.base import RateLimiter
from app.adapters.sockets.fred import FRED_API_KEY_ENV_VAR, FredAdapter, FredConfigError
from app.core.secrets import mask_secret

FRED_PAYLOAD = {
    "observations": [
        {"date": "2026-06-01", "value": "5.25"},
        {"date": "2026-07-01", "value": "."},  # FRED-Markierung für fehlende Beobachtung
        {"date": "2026-08-01", "value": "5.30"},
    ]
}


def _fake_http_get(_url: str) -> bytes:
    return json.dumps(FRED_PAYLOAD).encode()


def test_raises_without_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    """@trace dateneingang#AC3 — ohne konfigurierten API-Key (weder
    Konstruktor-Parameter noch Env-Var) wird der Adapter nicht instanziiert."""
    monkeypatch.delenv(FRED_API_KEY_ENV_VAR, raising=False)
    with pytest.raises(FredConfigError):
        FredAdapter(series_id="FEDFUNDS", anlageklassen_tag=9)


def test_reads_api_key_from_env_var(monkeypatch: pytest.MonkeyPatch) -> None:
    """@trace dateneingang#AC3 — der API-Key wird aus der Env-Var gelesen,
    nicht hartkodiert im Code übergeben."""
    monkeypatch.setenv(FRED_API_KEY_ENV_VAR, "geheim-123")

    adapter = FredAdapter(
        series_id="FEDFUNDS",
        anlageklassen_tag=9,
        http_get=_fake_http_get,
        rate_limiter=RateLimiter(0.0),
    )

    assert adapter is not None


def test_api_key_never_appears_in_cleartext_in_logs(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """@trace dateneingang#AC3 — der API-Key erscheint nie im Klartext in
    Log-Ausgaben, nur maskiert (`app.core.secrets.mask_secret`)."""
    caplog.set_level(logging.DEBUG, logger="app.adapters.sockets.fred")
    geheimer_key = "sk_live_ABCDEFGHIJ"

    FredAdapter(
        series_id="FEDFUNDS",
        anlageklassen_tag=9,
        api_key=geheimer_key,
        http_get=_fake_http_get,
        rate_limiter=RateLimiter(0.0),
    )

    assert geheimer_key not in caplog.text
    assert mask_secret(geheimer_key) in caplog.text


def test_fetch_normalizes_and_discards_missing_observation() -> None:
    """@trace dateneingang#AC1,AC2 — `fetch()` normalisiert FRED-
    Beobachtungen auf den einheitlichen Datenpunkt (AC1) und verwirft die
    mit "." markierte fehlende Beobachtung mangels Qualitätsindikator
    (AC2), statt sie zu schätzen."""
    adapter = FredAdapter(
        series_id="FEDFUNDS",
        anlageklassen_tag=9,
        api_key="test-key",
        http_get=_fake_http_get,
        rate_limiter=RateLimiter(0.0),
    )

    punkte = asyncio.run(adapter.fetch())

    assert len(punkte) == 2
    assert {p.wert for p in punkte} == {"5.25", "5.30"}
    for punkt in punkte:
        assert punkt.quelle == "fred"
        assert punkt.anlageklassen_tag == 9
        assert punkt.qualitaetsindikator == "roh"
    zeitstempel = {p.timestamp for p in punkte}
    assert datetime(2026, 6, 1, tzinfo=UTC) in zeitstempel
    assert datetime(2026, 8, 1, tzinfo=UTC) in zeitstempel


def test_fetch_respects_rate_limiter() -> None:
    """@trace dateneingang#AC3 — `fetch()` wartet vor jedem Abruf über den
    injizierten `RateLimiter` (Rate-Limit ist je Quelle im Adapter
    gekapselt, nicht global)."""
    calls: list[float] = []

    async def spy_sleep(seconds: float) -> None:
        calls.append(seconds)

    clock_values = iter([100.0, 100.0, 100.1, 100.1])

    def fake_monotonic() -> float:
        return next(clock_values)

    limiter = RateLimiter(5.0, sleep=spy_sleep, monotonic=fake_monotonic)
    adapter = FredAdapter(
        series_id="FEDFUNDS",
        anlageklassen_tag=9,
        api_key="test-key",
        http_get=_fake_http_get,
        rate_limiter=limiter,
    )

    asyncio.run(adapter.fetch())
    asyncio.run(adapter.fetch())

    assert calls == pytest.approx([4.9])
