"""Tests für `SqlAlchemyKandidatenRepository` (Story S-066/S-072,
`docs/specs/frontend-cockpit.md` AC4/AC5/AC7/AC15).

Covers (frontend-cockpit): AC4, AC5, AC7, AC15 — AC7 (Read-Modell-Gap
geschlossen) ist kein eigenes Test-Case, sondern strukturell durch diese
Datei erfüllt: sie prüft genau den Adapter, der die Kandidaten-Analysen
erstmals als persistentes, HTTP-abfragbares Read-Modell exponiert (rein
lesend, kein `session.add`/`commit` in keinem Test hier). AC15 (S-072
Iteration 2, Review-Fund): `sanity_cap_angewendet` auf `liste_kandidaten`
— Grundlage des §7.7-Signal-Badge-Markers.

Prüft `app.adapters.repositories.analysis_result_repository
.SqlAlchemyKandidatenRepository` gegen eine SQLite-In-Memory-DB: nur
vollständig bewertete Analysen erscheinen in `liste_kandidaten` (AC4),
`kandidat_detail` liefert auch eine übersprungene Analyse mit als fehlend
ausgewiesenen Kategorien (AC5, deckt E3), und eine unbekannte/ungültige ID
liefert `None` statt einer Exception (HTTP-404-Grundlage)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.adapters.repositories.analysis_result_repository import SqlAlchemyKandidatenRepository
from app.db.base import Base
from app.db.models import (
    AnalysisCategory,
    AnalysisCategoryScore,
    AnalysisFact,
    AnalysisMethodVersion,
    AnalysisResult,
    AssetClass,
    CategoryWeightVersion,
    DataSource,
    Instrument,
)

_KATEGORIE_CODES = ("fundamental", "technisch", "qualitativ", "makro", "risiko_quant")


def _session() -> Session:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return Session(engine)


def _stammdaten(session: Session) -> dict[str, object]:
    asset_class = AssetClass(id=1, name="Aktien", prio_stufe="MVP", aktiv=True)
    instrument = Instrument(
        id=uuid.uuid4(), symbol="AAPL", name="Apple", asset_class_id=1, currency="USD"
    )
    category_weight_version = CategoryWeightVersion(id=uuid.uuid4())
    analysis_method_version = AnalysisMethodVersion(id=uuid.uuid4())
    data_source = DataSource(id=uuid.uuid4(), name="SEC Form 4", frequenz_sekunden=3600)
    kategorien = [AnalysisCategory(code=code, name=code) for code in _KATEGORIE_CODES]
    session.add_all(
        [
            asset_class,
            instrument,
            category_weight_version,
            analysis_method_version,
            data_source,
            *kategorien,
        ]
    )
    session.commit()
    return {
        "asset_class_id": asset_class.id,
        "instrument_id": instrument.id,
        "category_weight_version_id": category_weight_version.id,
        "analysis_method_version_id": analysis_method_version.id,
        "data_source_id": data_source.id,
    }


def _lege_analysis_result_an(
    session: Session,
    stammdaten: dict[str, object],
    *,
    gesamtscore: Decimal | None,
    signal_enum: str | None,
    kategorie_scores: dict[str, Decimal | None],
    sanity_cap_applied: bool = False,
    begruendung: str | None = None,
    created_at: datetime | None = None,
) -> AnalysisResult:
    ergebnis = AnalysisResult(
        id=uuid.uuid4(),
        instrument_id=stammdaten["instrument_id"],
        asset_class_id=stammdaten["asset_class_id"],
        category_weight_version_id=stammdaten["category_weight_version_id"],
        analysis_method_version_id=stammdaten["analysis_method_version_id"],
        analyse_typ="neue_titel",
        gesamtscore=gesamtscore,
        signal_enum=signal_enum,
        sanity_cap_applied=sanity_cap_applied,
        schema_valid=True,
        begruendung=begruendung,
    )
    if created_at is not None:
        ergebnis.created_at = created_at
    session.add(ergebnis)
    session.commit()

    for code, score in kategorie_scores.items():
        session.add(
            AnalysisCategoryScore(
                analysis_result_id=ergebnis.id,
                category_code=code,
                score=score,
                evidence_present=score is not None,
            )
        )
    session.commit()
    session.refresh(ergebnis)
    return ergebnis


_VOLLSTAENDIGE_SCORES = {
    "fundamental": Decimal("8"),
    "technisch": Decimal("7"),
    "qualitativ": Decimal("6"),
    "makro": Decimal("5"),
    "risiko_quant": Decimal("9"),
}


def test_liste_kandidaten_liefert_nur_vollstaendig_bewertete_analysen() -> None:
    """@trace frontend-cockpit#AC4 — eine übersprungene Analyse
    (`gesamtscore`/`signal_enum` NULL) erscheint NICHT in der Liste."""
    session = _session()
    stammdaten = _stammdaten(session)
    _lege_analysis_result_an(
        session,
        stammdaten,
        gesamtscore=Decimal("8.5"),
        signal_enum="KAUF",
        kategorie_scores=_VOLLSTAENDIGE_SCORES,
    )
    _lege_analysis_result_an(
        session,
        stammdaten,
        gesamtscore=None,
        signal_enum=None,
        kategorie_scores={"fundamental": None},
    )
    repository = SqlAlchemyKandidatenRepository(session)

    kandidaten = repository.liste_kandidaten()

    assert len(kandidaten) == 1
    assert kandidaten[0].gesamtscore == 8.5
    assert kandidaten[0].signal == "KAUF"


def test_liste_kandidaten_liefert_titel_symbol_und_name_aus_instrument() -> None:
    """@trace frontend-cockpit#AC4 — der menschenlesbare Titel (`symbol`/
    `name` aus `instrument`), nicht nur die rohe `instrument_id`."""
    session = _session()
    stammdaten = _stammdaten(session)
    _lege_analysis_result_an(
        session,
        stammdaten,
        gesamtscore=Decimal("8.5"),
        signal_enum="KAUF",
        kategorie_scores=_VOLLSTAENDIGE_SCORES,
    )
    repository = SqlAlchemyKandidatenRepository(session)

    kandidat = repository.liste_kandidaten()[0]

    assert kandidat.titel_id == str(stammdaten["instrument_id"])
    assert kandidat.titel == "AAPL"
    assert kandidat.name == "Apple"


def test_liste_kandidaten_liefert_alle_5_kategorie_scores_als_spinnennetz_achsen() -> None:
    """@trace frontend-cockpit#AC4 — die 5 Kategorie-Scores (Spinnennetz-
    Achsen, C-007) sind Teil jedes Listen-Eintrags."""
    session = _session()
    stammdaten = _stammdaten(session)
    _lege_analysis_result_an(
        session,
        stammdaten,
        gesamtscore=Decimal("8.5"),
        signal_enum="KAUF",
        kategorie_scores=_VOLLSTAENDIGE_SCORES,
    )
    repository = SqlAlchemyKandidatenRepository(session)

    kandidat = repository.liste_kandidaten()[0]

    assert kandidat.kategorie_scores.fundamental == 8.0
    assert kandidat.kategorie_scores.technisch == 7.0
    assert kandidat.kategorie_scores.qualitativ == 6.0
    assert kandidat.kategorie_scores.makro == 5.0
    assert kandidat.kategorie_scores.risiko == 9.0


def test_liste_kandidaten_liefert_sanity_cap_status() -> None:
    """@trace frontend-cockpit#AC15 — S-072 Iteration 2 (Review-Fund):
    `sanity_cap_angewendet` ist Teil jedes Listen-Eintrags (design.md
    §7.7-Marker auf dem Signal-Badge der Kandidaten-Tabelle, → BR-008),
    1:1 aus `AnalysisResult.sanity_cap_applied`."""
    session = _session()
    stammdaten = _stammdaten(session)
    _lege_analysis_result_an(
        session,
        stammdaten,
        gesamtscore=Decimal("4.5"),
        signal_enum="HALTEN",
        kategorie_scores=_VOLLSTAENDIGE_SCORES,
        sanity_cap_applied=True,
    )
    repository = SqlAlchemyKandidatenRepository(session)

    kandidat = repository.liste_kandidaten()[0]

    assert kandidat.sanity_cap_angewendet is True


def test_liste_kandidaten_sortiert_neueste_zuerst() -> None:
    """@trace frontend-cockpit#AC4 — `as_of` absteigend (neueste Analyse
    zuerst)."""
    session = _session()
    stammdaten = _stammdaten(session)
    aeltere = _lege_analysis_result_an(
        session,
        stammdaten,
        gesamtscore=Decimal("7"),
        signal_enum="BEOBACHTEN",
        kategorie_scores=_VOLLSTAENDIGE_SCORES,
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
    )
    neuere = _lege_analysis_result_an(
        session,
        stammdaten,
        gesamtscore=Decimal("9"),
        signal_enum="KAUF",
        kategorie_scores=_VOLLSTAENDIGE_SCORES,
        created_at=datetime(2026, 6, 1, tzinfo=UTC),
    )
    repository = SqlAlchemyKandidatenRepository(session)

    kandidaten = repository.liste_kandidaten()

    assert [k.analysis_result_id for k in kandidaten] == [str(neuere.id), str(aeltere.id)]


def test_kandidat_detail_liefert_fakten_begruendung_und_sanity_cap_status() -> None:
    """@trace frontend-cockpit#AC5 — Kategorie-Fakten inkl. Quellen-ID +
    Timestamp (→ BR-002), Begründung, Sanity-Cap-Status (→ BR-008)."""
    session = _session()
    stammdaten = _stammdaten(session)
    ergebnis = _lege_analysis_result_an(
        session,
        stammdaten,
        gesamtscore=Decimal("4.5"),
        signal_enum="HALTEN",
        kategorie_scores=_VOLLSTAENDIGE_SCORES,
        sanity_cap_applied=True,
        begruendung="Risiko-Score unter 3 — Sanity-Cap greift.",
    )
    session.add(
        AnalysisFact(
            id=uuid.uuid4(),
            analysis_result_id=ergebnis.id,
            kennzahl="kgv",
            wert=Decimal("15.5"),
            source_id=stammdaten["data_source_id"],
            source_timestamp=datetime(2026, 7, 1, tzinfo=UTC),
        )
    )
    session.commit()
    repository = SqlAlchemyKandidatenRepository(session)

    detail = repository.kandidat_detail(str(ergebnis.id))

    assert detail is not None
    assert detail.titel == "AAPL"
    assert detail.name == "Apple"
    assert detail.sanity_cap_angewendet is True
    assert detail.begruendung == "Risiko-Score unter 3 — Sanity-Cap greift."
    assert len(detail.fakten) == 1
    assert detail.fakten[0].kennzahl == "kgv"
    assert detail.fakten[0].quellen_id == str(stammdaten["data_source_id"])
    # SQLite (Test-Backend) liefert `tzinfo` bei TIMESTAMPTZ-Spalten nicht
    # zurueck (anders als Postgres) — Vergleich UTC-naiv (analog
    # `app.db.utils.als_utc_naiv`-Konvention).
    assert detail.fakten[0].zeitstempel.replace(tzinfo=None) == datetime(2026, 7, 1)


def test_kandidat_detail_weist_fehlende_kategorie_als_none_aus_statt_zu_schaetzen() -> None:
    """@trace frontend-cockpit#AC5 — deckt E3: fehlt die Datengrundlage
    einer Kategorie, wird sie als fehlend (`None`) ausgewiesen, nie
    geschätzt — auch bei einer wegen No-Evidence-No-Trade übersprungenen
    Analyse (→ BR-005)."""
    session = _session()
    stammdaten = _stammdaten(session)
    scores = dict(_VOLLSTAENDIGE_SCORES)
    scores["risiko_quant"] = None
    ergebnis = _lege_analysis_result_an(
        session,
        stammdaten,
        gesamtscore=None,
        signal_enum=None,
        kategorie_scores=scores,
    )
    repository = SqlAlchemyKandidatenRepository(session)

    detail = repository.kandidat_detail(str(ergebnis.id))

    assert detail is not None
    assert detail.gesamtscore is None
    assert detail.signal is None
    assert detail.kategorie_scores.risiko is None
    assert detail.kategorie_scores.fundamental == 8.0


def test_kandidat_detail_liefert_none_fuer_unbekannte_id() -> None:
    """@trace frontend-cockpit#AC5 — Grundlage für den HTTP-404-Fehlerpfad
    der Route."""
    session = _session()
    _stammdaten(session)
    repository = SqlAlchemyKandidatenRepository(session)

    assert repository.kandidat_detail(str(uuid.uuid4())) is None


def test_kandidat_detail_liefert_none_fuer_ungueltige_id() -> None:
    """@trace frontend-cockpit#AC5 — keine gültige UUID → `None` statt
    einer Exception."""
    session = _session()
    _stammdaten(session)
    repository = SqlAlchemyKandidatenRepository(session)

    assert repository.kandidat_detail("keine-uuid") is None
