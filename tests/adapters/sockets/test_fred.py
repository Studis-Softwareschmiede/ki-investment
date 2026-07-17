"""Tests für den FRED-Adapter (Story S-005, konkrete Referenzimplementierung
von `SocketAdapter`; Story S-050 ergänzt das Recalculation-Window).

Covers (dateneingang): AC1, AC2, AC3, AC12

`app.adapters.sockets.fred.FredAdapter` ist die erste konkrete
Quellen-Implementierung des Adapter-Ports (AC1). Diese Tests decken: Auth
per API-Key aus Env-Var, ohne Key keine Instanziierung (AC3); der Key
erscheint nie im Klartext in Logs, nur maskiert (AC3,
`app.core.secrets.mask_secret`); FRED-typische fehlende Beobachtungen
(`"."`) werden mangels Qualitätsindikator verworfen, nicht geschätzt
(AC2); die normalisierten Datenpunkte tragen alle vier Pflicht-Metadaten
(AC1/AC2); das Rate-Limit ist im Adapter gekapselt (AC3); das
Recalculation-Window (AC12/A2) wird bei jedem Abruf als
`observation_start` an die FRED-API übergeben — konfigurierbar per
Konstruktor-Parameter oder `Settings.fred_recalculation_window_tage`
(Default 3 Tage, `FRED_RECALCULATION_WINDOW_TAGE`).
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import UTC, datetime
from urllib.parse import parse_qs, urlparse

import pytest

from app.adapters.sockets.base import RateLimiter
from app.adapters.sockets.fred import FRED_API_KEY_ENV_VAR, FredAdapter, FredConfigError
from app.config import get_settings
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
    # Fake-Wert, kein echtes Secret-Muster (gitleaks-FP-Fix) — gitleaks:allow
    geheimer_key = "dummy-fixture-secret-42"  # gitleaks:allow

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


def test_fetch_uses_configured_recalculation_window_as_observation_start() -> None:
    """@trace dateneingang#AC12 — der Adapter übergibt `observation_start`
    als `jetzt - recalculation_window_tage` an die FRED-API (A2: die
    letzten Tage werden bei jedem Abruf erneut gezogen, um rückwirkende
    Korrekturen zu erfassen)."""
    erfasste_urls: list[str] = []

    def _spy_http_get(url: str) -> bytes:
        erfasste_urls.append(url)
        return json.dumps(FRED_PAYLOAD).encode()

    adapter = FredAdapter(
        series_id="FEDFUNDS",
        anlageklassen_tag=9,
        api_key="test-key",
        http_get=_spy_http_get,
        rate_limiter=RateLimiter(0.0),
        recalculation_window_tage=5,
        jetzt=lambda: datetime(2026, 7, 18, tzinfo=UTC),
    )

    asyncio.run(adapter.fetch())

    assert len(erfasste_urls) == 1
    query = parse_qs(urlparse(erfasste_urls[0]).query)
    assert query["observation_start"] == ["2026-07-13"]


def test_fetch_recalculation_window_defaults_from_settings(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """@trace dateneingang#AC12 — ohne expliziten Konstruktor-Parameter
    wird die Fensterbreite aus `Settings.fred_recalculation_window_tage`
    gelesen (Default 3 Tage, ohne Codeänderung über
    `FRED_RECALCULATION_WINDOW_TAGE` überschreibbar)."""
    monkeypatch.setenv("FRED_RECALCULATION_WINDOW_TAGE", "7")
    get_settings.cache_clear()
    try:
        erfasste_urls: list[str] = []

        def _spy_http_get(url: str) -> bytes:
            erfasste_urls.append(url)
            return json.dumps(FRED_PAYLOAD).encode()

        adapter = FredAdapter(
            series_id="FEDFUNDS",
            anlageklassen_tag=9,
            api_key="test-key",
            http_get=_spy_http_get,
            rate_limiter=RateLimiter(0.0),
            jetzt=lambda: datetime(2026, 7, 18, tzinfo=UTC),
        )

        asyncio.run(adapter.fetch())

        query = parse_qs(urlparse(erfasste_urls[0]).query)
        assert query["observation_start"] == ["2026-07-11"]
    finally:
        get_settings.cache_clear()


def test_fetch_recalculation_window_repull_is_idempotent_on_unchanged_value() -> None:
    """@trace dateneingang#AC12 — zwei aufeinanderfolgende Abrufe desselben
    (unveränderten) Fensters liefern inhaltlich identische Datenpunkte
    (Vorbedingung für die idempotente Bronze-Aktualisierung, S-022) — kein
    unbeabsichtigter Doppel-/Drift-Effekt allein durch das erneute Ziehen."""
    adapter = FredAdapter(
        series_id="FEDFUNDS",
        anlageklassen_tag=9,
        api_key="test-key",
        http_get=_fake_http_get,
        rate_limiter=RateLimiter(0.0),
        recalculation_window_tage=3,
    )

    erster_durchlauf = asyncio.run(adapter.fetch())
    zweiter_durchlauf = asyncio.run(adapter.fetch())

    assert {p.wert for p in erster_durchlauf} == {p.wert for p in zweiter_durchlauf}
