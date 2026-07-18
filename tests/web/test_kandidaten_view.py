"""Tests für die Kandidaten-View (`app/api/ui.py` Routen `/ui/kandidaten`
+ `/ui/kandidaten/{id}`, `app/web/templates/views/kandidaten.html` +
`app/web/templates/partials/kandidaten/**`, Story S-072).

Covers (frontend-cockpit): AC15

HTTP-/Router-Ebenen-Test (coder/R06): deckt den vollen Pfad
Request→Router→Jinja2-Rendering→Response-Body für BEIDE neuen Routen ab
(Status-Code + gerenderte HTML-Struktur) — Fake-`KandidatenRepository` via
`app.dependency_overrides` (fastapi/A09, analog `tests/api/
test_kandidaten.py`), keine echte DB nötig. Deckt: Kandidaten-Tabelle
(Titel/Klassen-Chip/Gesamtscore+Signal-Badge/as_of, AC15-a), leere Liste
(Empty-State), Detail-Panel-HTMX-Partial mit vollständigen Kategorie-
Scores (Spinnennetz-Kaufstärke-Fläche + Werttabelle + Kategorie-Fakten +
Sanity-Cap-Hinweis, AC15-b/c/d), fehlende Kategorie (E3/BR-005: keine
Kaufstärke-Fläche, Werttabelle zeigt "—"), Sanity-Cap aktiv (Risiko-Achse
mit Warn-Marker), unbekannte ID (definierter "nicht gefunden"-Zustand,
kein 500/Crash), sowie die HTMX-Verdrahtung des "Öffnen"-Buttons
(hx-get/hx-target/hx-swap, AC15-e).

**S-072 Iteration 2 (Review-Fund):** zusätzlich der design.md §7.7-
Sanity-Cap-Marker + `data-sanity-capped`-Attribut auf dem Signal-Badge
DER KANDIDATEN-TABELLE (nicht nur im Detail-Panel), der Gesamtscore-
Mini-Meter (§7.7) sowie der Fokus-Sprung auf die Detail-Überschrift nach
dem HTMX-Swap (A11y-Suggestion, AC15-e)."""

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


def _client(repository: object) -> TestClient:
    app.dependency_overrides[get_kandidaten_repository] = lambda: repository
    return TestClient(app)


@pytest.fixture(autouse=True)
def _reset_overrides():
    yield
    app.dependency_overrides.clear()


def _kandidat(
    *,
    analysis_result_id: str = "a1",
    titel: str = "AAPL",
    asset_class_id: int = 1,
    gesamtscore: float = 8.5,
    signal: str = "KAUF",
    sanity_cap_angewendet: bool = False,
) -> KandidatUebersicht:
    return KandidatUebersicht(
        analysis_result_id=analysis_result_id,
        titel_id="titel-1",
        titel=titel,
        name="Apple",
        asset_class_id=asset_class_id,
        gesamtscore=gesamtscore,
        signal=signal,
        kategorie_scores=_VOLLSTAENDIGE_SCORES,
        as_of=datetime(2026, 7, 1, 10, 0, tzinfo=UTC),
        sanity_cap_angewendet=sanity_cap_angewendet,
    )


def test_kandidaten_view_antwortet_200() -> None:
    client = _client(_FakeKandidatenRepository())
    resp = client.get("/ui/kandidaten")
    assert resp.status_code == 200


def test_kandidaten_tabelle_zeigt_titel_klasse_score_signal_und_as_of() -> None:
    """@trace frontend-cockpit#AC15 — Kandidaten-Tabelle (§7.6): Titel,
    Klassen-Chip, Gesamtscore + Signal-Badge (§7.7), as_of."""
    client = _client(_FakeKandidatenRepository(kandidaten=[_kandidat()]))

    html = client.get("/ui/kandidaten").text

    assert 'data-testid="table-kandidaten"' in html
    assert 'data-testid="kandidat-row"' in html
    assert 'data-row-id="a1"' in html
    assert "AAPL" in html
    assert 'data-testid="klassen-chip"' in html
    assert 'data-anlageklasse="akt"' in html  # asset_class_id=1 -> AKT
    assert "8.5" in html
    assert 'data-testid="signal-badge"' in html
    assert 'data-signal="kauf"' in html
    assert "KAUF" in html
    assert "2026-07-01" in html


def test_kandidaten_tabelle_zeigt_gesamtscore_mini_meter() -> None:
    """@trace frontend-cockpit#AC15 — design.md §7.7: horizontaler
    0–10-Mini-Meter zusätzlich zum Zahlenwert; A11y: der Zahlenwert bleibt
    der zugängliche Text (`role="presentation"` auf dem Meter)."""
    client = _client(_FakeKandidatenRepository(kandidaten=[_kandidat(gesamtscore=8.5)]))

    html = client.get("/ui/kandidaten").text

    assert 'data-testid="score-meter"' in html
    assert 'role="presentation"' in html
    assert "width: 85.0%" in html


def test_kandidaten_tabelle_signal_badge_ohne_sanity_cap_traegt_data_attribut_false() -> None:
    """@trace frontend-cockpit#AC15 — design.md §7.7/BR-008: das
    `data-sanity-capped`-Anker-Attribut steht auf JEDEM Signal-Badge der
    Tabelle, nicht nur im Detail-Panel."""
    client = _client(_FakeKandidatenRepository(kandidaten=[_kandidat(sanity_cap_angewendet=False)]))

    html = client.get("/ui/kandidaten").text

    badge_start = html.index('data-testid="signal-badge"')
    badge_block = html[badge_start : badge_start + 300]
    assert 'data-sanity-capped="false"' in badge_block
    assert "gedeckelt" not in badge_block


def test_kandidaten_tabelle_signal_badge_mit_sanity_cap_zeigt_marker() -> None:
    """@trace frontend-cockpit#AC15 — design.md §7.7: ist der Sanity-Cap
    (BR-008) aktiv, trägt das Signal-Badge der Tabelle den Zusatz-Marker
    "⛨ gedeckelt (Risiko<3)" UND `data-sanity-capped="true"`."""
    client = _client(_FakeKandidatenRepository(kandidaten=[_kandidat(sanity_cap_angewendet=True)]))

    html = client.get("/ui/kandidaten").text

    badge_start = html.index('data-testid="signal-badge"')
    badge_block = html[badge_start : badge_start + 300]
    assert 'data-sanity-capped="true"' in badge_block
    assert "⛨ gedeckelt (Risiko&lt;3)" in badge_block


def test_kandidaten_tabelle_zeigt_definierten_empty_state() -> None:
    """@trace frontend-cockpit#AC15 — §7.6 Empty/No-Data: eigener leerer
    Zustand statt leerer Tabelle."""
    client = _client(_FakeKandidatenRepository())

    html = client.get("/ui/kandidaten").text

    assert 'data-testid="kandidaten-leer"' in html
    assert 'data-testid="table-kandidaten"' not in html


def test_kandidat_open_button_traegt_htmx_partial_load_verdrahtung() -> None:
    """@trace frontend-cockpit#AC15 — AC15-e: HTMX fürs Detail-Panel
    (Partial-Load)."""
    client = _client(_FakeKandidatenRepository(kandidaten=[_kandidat()]))

    html = client.get("/ui/kandidaten").text

    assert 'data-testid="kandidat-open"' in html
    assert 'hx-get="' in html
    assert '/ui/kandidaten/a1"' in html  # url_for liefert eine absolute URL
    assert 'hx-target="#kandidat-detail"' in html
    assert 'hx-swap="outerHTML"' in html
    assert "hx-on::after-swap=" in html


def test_kandidaten_view_zeigt_initial_leeren_detail_zustand() -> None:
    client = _client(_FakeKandidatenRepository(kandidaten=[_kandidat()]))

    html = client.get("/ui/kandidaten").text

    assert 'data-testid="kandidat-detail"' in html
    assert 'data-testid="kandidat-detail-leer"' in html


def test_kandidat_detail_partial_antwortet_200_ohne_seiten_layout() -> None:
    """Die Partial-Route liefert NUR den Detail-Container, kein volles
    Seiten-Layout (kein `<header>`/`<nav>` der Shell) — sonst würde der
    HTMX-Swap die komplette Shell in den Zielcontainer einfügen."""
    detail = KandidatDetail(
        analysis_result_id="a1",
        titel_id="titel-1",
        titel="AAPL",
        name="Apple",
        asset_class_id=1,
        gesamtscore=8.5,
        signal="KAUF",
        kategorie_scores=_VOLLSTAENDIGE_SCORES,
        sanity_cap_angewendet=False,
        begruendung=None,
        fakten=(),
        as_of=datetime(2026, 7, 1, 10, 0, tzinfo=UTC),
    )
    client = _client(_FakeKandidatenRepository(details={"a1": detail}))

    resp = client.get("/ui/kandidaten/a1")

    assert resp.status_code == 200
    assert "<header" not in resp.text
    assert "<nav" not in resp.text


def test_kandidat_detail_partial_zeigt_spinnennetz_werttabelle_und_fakten() -> None:
    """@trace frontend-cockpit#AC15 — AC15-b/c/d: Spinnennetz-SVG
    (role="img" + aria-label), begleitende Kategorie-Score-Werttabelle,
    Kategorie-Fakten (Quellen-ID/Timestamp)."""
    detail = KandidatDetail(
        analysis_result_id="a1",
        titel_id="titel-1",
        titel="AAPL",
        name="Apple",
        asset_class_id=1,
        gesamtscore=8.5,
        signal="KAUF",
        kategorie_scores=_VOLLSTAENDIGE_SCORES,
        sanity_cap_angewendet=False,
        begruendung=None,
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

    html = client.get("/ui/kandidaten/a1").text

    assert 'class="kandidat-detail-titel" tabindex="-1"' in html
    assert 'data-testid="spinnennetz"' in html
    assert 'role="img"' in html
    assert 'aria-label="Analyse AAPL: Fundamental 8.0, Technisch 7.0' in html
    assert 'data-series="aktuell"' in html
    for kategorie in ("fundamental", "technisch", "qualitativ", "makro", "risiko"):
        assert f'data-kategorie="{kategorie}"' in html
    assert 'data-testid="kategorie-werttabelle"' in html
    assert 'data-testid="kategorie-fakten"' in html
    assert "kgv" in html
    assert "15.5" in html
    assert "quelle-1" in html
    assert 'data-testid="sanity-cap-hinweis"' in html
    assert 'data-sanity-capped="false"' in html


def test_kandidat_detail_partial_fehlende_kategorie_baut_keine_kaufstaerke_flaeche() -> None:
    """@trace frontend-cockpit#AC15 — deckt E3/BR-005: fehlt eine
    Kategorie, wird sie als fehlend ausgewiesen (Werttabelle "—"), nie
    geschätzt; die Spinnennetz-Kaufstärke-Fläche wird dann NICHT
    gezeichnet (kein fabrizierter Polygon-Punkt)."""
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

    html = client.get("/ui/kandidaten/a1").text

    assert 'class="spinnennetz-flaeche"' not in html
    risiko_block_start = html.index('data-kategorie="risiko"')
    risiko_block = html[risiko_block_start : risiko_block_start + 200]
    assert 'data-score=""' in risiko_block
    assert "fehlend" in html  # aria-label
    assert 'data-testid="kategorie-fakten-leer"' in html


def test_kandidat_detail_partial_sanity_cap_aktiv_markiert_risiko_achse() -> None:
    """@trace frontend-cockpit#AC15 — BR-008: Sanity-Cap-Hinweis + Risiko-
    Achsen-Warn-Marker (design.md §8.1)."""
    detail = KandidatDetail(
        analysis_result_id="a1",
        titel_id="titel-1",
        titel="AAPL",
        name="Apple",
        asset_class_id=1,
        gesamtscore=4.5,
        signal="HALTEN",
        kategorie_scores=KategorieScores(
            fundamental=8.0, technisch=7.0, qualitativ=6.0, makro=5.0, risiko=2.0
        ),
        sanity_cap_angewendet=True,
        begruendung="Risiko-Score unter 3 — Sanity-Cap greift.",
        fakten=(),
        as_of=datetime(2026, 7, 1, 10, 0, tzinfo=UTC),
    )
    client = _client(_FakeKandidatenRepository(details={"a1": detail}))

    html = client.get("/ui/kandidaten/a1").text

    assert 'data-sanity-capped="true"' in html
    assert "gedeckelt" in html
    assert "spinnennetz-achse--warn" in html


def test_kandidat_detail_partial_liefert_definierten_nicht_gefunden_zustand() -> None:
    """Unbekannte `analysis_result_id`: HTTP 200 mit definiertem Leer-/
    Fehlerzustand statt Crash (die HTML-Partial-Route unterscheidet sich
    hier bewusst von der JSON-API, die 404 liefert, AC5)."""
    client = _client(_FakeKandidatenRepository())

    resp = client.get("/ui/kandidaten/unbekannt")

    assert resp.status_code == 200
    assert 'data-testid="kandidat-detail-nicht-gefunden"' in resp.text
