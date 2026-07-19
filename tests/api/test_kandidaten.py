"""Tests für die Kandidaten-Endpunkte (`app.api.kandidaten`, Story S-066,
`docs/specs/frontend-cockpit.md` AC4/AC5).

Covers (frontend-cockpit): AC4, AC5

HTTP-/Router-Ebenen-Test (coder/R06): deckt den vollen Pfad
Request→Router→Response-Body für `GET /api/kandidaten` und
`GET /api/kandidaten/{id}` ab (Status-Code + Body-Shape) — Fake-
`KandidatenRepository` via `app.dependency_overrides` (fastapi/A09), keine
echte DB nötig (reine Anzeige-Schicht). Deckt: leere Liste, vollständig
bewerteter Kandidat mit 5 Kategorie-Scores + Signal, Detail mit Fakten/
Begründung/Sanity-Cap-Status, fehlende Kategorie als `null` (nie geschätzt,
deckt E3), 404 für eine unbekannte ID."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient

from app.api.kandidaten import get_kandidaten_repository
from app.contracts.analyse_framework import KategorieScores
from app.domain.scoring.ports import KandidatDetail, KandidatFakt, KandidatUebersicht
from app.main import app

_VOLLSTAENDIGE_SCORES = KategorieScores(
    fundamental=8.0, technisch=7.0, qualitativ=6.0, makro=5.0, risiko=9.0
)


class _FakeKandidatenRepository:
    def __init__(
        self,
        *,
        kandidaten: list[KandidatUebersicht] | None = None,
        details: dict[str, KandidatDetail] | None = None,
    ):
        self._kandidaten = kandidaten or []
        self._details = details or {}

    def liste_kandidaten(self) -> list[KandidatUebersicht]:
        return self._kandidaten

    def kandidat_detail(self, analysis_result_id: str) -> KandidatDetail | None:
        return self._details.get(analysis_result_id)


def _client(repository) -> TestClient:
    app.dependency_overrides[get_kandidaten_repository] = lambda: repository
    return TestClient(app)


@pytest.fixture(autouse=True)
def _reset_overrides():
    yield
    app.dependency_overrides.clear()


def test_leere_kandidatenliste() -> None:
    client = _client(_FakeKandidatenRepository())

    resp = client.get("/api/kandidaten")

    assert resp.status_code == 200
    assert resp.json() == []


def test_kandidatenliste_liefert_titel_klasse_score_signal_kategorie_scores_und_as_of() -> None:
    kandidat = KandidatUebersicht(
        analysis_result_id="a1",
        titel_id="titel-1",
        titel="AAPL",
        name="Apple",
        asset_class_id=1,
        gesamtscore=8.5,
        signal="KAUF",
        kategorie_scores=_VOLLSTAENDIGE_SCORES,
        as_of=datetime(2026, 7, 1, 10, 0, tzinfo=UTC),
        sanity_cap_angewendet=False,
    )
    client = _client(_FakeKandidatenRepository(kandidaten=[kandidat]))

    resp = client.get("/api/kandidaten")

    assert resp.status_code == 200
    eintrag = resp.json()[0]
    assert eintrag["analysis_result_id"] == "a1"
    assert eintrag["titel_id"] == "titel-1"
    assert eintrag["titel"] == "AAPL"
    assert eintrag["name"] == "Apple"
    assert eintrag["asset_class_id"] == 1
    assert eintrag["gesamtscore"] == 8.5
    assert eintrag["signal"] == "KAUF"
    assert eintrag["kategorie_scores"] == {
        "fundamental": 8.0,
        "technisch": 7.0,
        "qualitativ": 6.0,
        "makro": 5.0,
        "risiko": 9.0,
    }
    assert eintrag["as_of"] == "2026-07-01T10:00:00Z"
    assert eintrag["sanity_cap_angewendet"] is False


def test_kandidat_detail_liefert_fakten_begruendung_und_sanity_cap_status() -> None:
    detail = KandidatDetail(
        analysis_result_id="a1",
        titel_id="titel-1",
        titel="AAPL",
        name="Apple",
        asset_class_id=1,
        gesamtscore=4.5,
        signal="HALTEN",
        kategorie_scores=_VOLLSTAENDIGE_SCORES,
        sanity_cap_angewendet=True,
        begruendung="Risiko-Score unter 3 — Sanity-Cap greift.",
        fakten=(
            KandidatFakt(
                kennzahl="kgv",
                wert=Decimal("15.5"),
                quellen_id="quelle-1",
                zeitstempel=datetime(2026, 7, 1, tzinfo=UTC),
            ),
        ),
        as_of=datetime(2026, 7, 1, 10, 0, tzinfo=UTC),
    )
    client = _client(_FakeKandidatenRepository(details={"a1": detail}))

    resp = client.get("/api/kandidaten/a1")

    assert resp.status_code == 200
    body = resp.json()
    assert body["titel"] == "AAPL"
    assert body["name"] == "Apple"
    assert body["sanity_cap_angewendet"] is True
    assert body["begruendung"] == "Risiko-Score unter 3 — Sanity-Cap greift."
    assert body["fakten"] == [
        {
            "kennzahl": "kgv",
            "wert": "15.5",
            "quellen_id": "quelle-1",
            "zeitstempel": "2026-07-01T00:00:00Z",
        }
    ]


def test_kandidat_detail_weist_fehlende_kategorie_als_null_aus() -> None:
    """@trace frontend-cockpit#AC5 — deckt E3: fehlende Kategorie wird als
    `null` ausgewiesen, nie geschätzt; `gesamtscore`/`signal` bleiben
    ebenfalls `null` (No-Evidence-No-Trade-Übersprung)."""
    detail = KandidatDetail(
        analysis_result_id="a1",
        titel_id="titel-1",
        titel="AAPL",
        name="Apple",
        asset_class_id=1,
        gesamtscore=None,
        signal=None,
        kategorie_scores=KategorieScores(
            fundamental=8.0, technisch=7.0, qualitativ=6.0, makro=5.0, risiko=None
        ),
        sanity_cap_angewendet=False,
        begruendung=None,
        fakten=(),
        as_of=datetime(2026, 7, 1, 10, 0, tzinfo=UTC),
    )
    client = _client(_FakeKandidatenRepository(details={"a1": detail}))

    resp = client.get("/api/kandidaten/a1")

    assert resp.status_code == 200
    body = resp.json()
    assert body["gesamtscore"] is None
    assert body["signal"] is None
    assert body["kategorie_scores"]["risiko"] is None


def test_kandidat_detail_liefert_404_fuer_unbekannte_id() -> None:
    client = _client(_FakeKandidatenRepository())

    resp = client.get("/api/kandidaten/unbekannt")

    assert resp.status_code == 404
