"""Tests fuer den Validierungs-Layer `app.db.validation` (Story S-023).

Covers (datenqualitaet): AC7, AC8

- AC7 (Pflicht-Regeln, ab MVP aktiv, nicht abschaltbar): jede der drei
  Regel-Kategorien (Schema/Feldtypen, erlaubte Wertebereiche,
  Pflicht-Metadaten-Vollstaendigkeit) wird einzeln negativ geprueft; ein
  vollstaendig gueltiger Kandidat liefert `valide=True` mit leerer
  `verletzte_regeln`-Liste. Der Edge-Case "Event-ID kollidiert mit
  inhaltlich abweichendem Datenpunkt" (Spec Edge-Cases-Abschnitt, laut
  S-022-Handoff dieser Story zugeordnet) wird von einer legitimen Revision
  (AC10/A1 — gleicher `beobachtungs_zeitpunkt`, neuer Wert) unterschieden:
  nur ein ABWEICHENDER `beobachtungs_zeitpunkt` bei kollidierender Event-ID
  ist ein Validierungsfehler.
- AC8 (verwerfen + protokollieren, deckt E1): ein ungueltiger Kandidat
  bekommt `valide=False`, fuehrt zu KEINEM `logger.warning`-Aufruf bei
  gueltigen Kandidaten, aber zu genau einem strukturierten
  `logger.warning`-Log mit den verletzten Regeln bei ungueltigen
  Kandidaten (geprueft via `caplog`).

`anlageklassen_tag` ist laut `docs/data-model.md` §2 physisch nullable und
laut Spec-Praezisierung (`docs/specs/datenqualitaet.md`, Vertrag
"Validierungs-Ergebnis") daher NICHT Teil der Pflicht-Metadaten-
Vollstaendigkeit — nur, sofern gesetzt, der Wertebereichspruefung
unterworfen; ein Test belegt das explizit.

SQLite (in-memory) reicht aus (reiner SQLAlchemy-/Python-Code, kein
Postgres-spezifisches Konstrukt), analog `tests/db/test_bronze.py`.
"""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.db.base import Base
from app.db.bronze import record_observation
from app.db.models import AssetClass, DataSource, MarketDataBronze
from app.db.validation import (
    REGEL_ANLAGEKLASSEN_TAG_AUSSERHALB_WERTEBEREICH,
    REGEL_ANLAGEKLASSEN_TAG_FALSCHER_TYP,
    REGEL_BEOBACHTUNGS_ZEITPUNKT_FALSCHER_TYP,
    REGEL_BEOBACHTUNGS_ZEITPUNKT_FEHLT,
    REGEL_EVENT_ID_FEHLT,
    REGEL_EVENT_ID_KOLLISION,
    REGEL_QUELLE_FEHLT,
    REGEL_ROH_WERT_FEHLT,
    validate_bronze_kandidat,
)


@pytest.fixture()
def session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as db_session:
        db_session.add(
            AssetClass(
                id=3, name="Cash/Geldmarkt", prio_stufe="MVP", aktiv=True, retail_driven=False
            )
        )
        db_session.add(
            DataSource(
                id=uuid.uuid4(),
                name="FRED - Federal Reserve Economic Data",
                kategorie="makro_anleihen",
                qualitaet="sehr_hoch",
                frequenz_sekunden=86400,
                aktiv=True,
            )
        )
        db_session.commit()
        yield db_session


def _fred_source_id(session: Session) -> uuid.UUID:
    return session.query(DataSource).one().id


def test_valid_candidate_is_marked_valid_with_no_violations(session: Session) -> None:
    """@trace datenqualitaet#AC7 — ein vollstaendig gueltiger Bronze-
    Kandidat (Schema/Feldtypen ok, Wertebereich ok, Pflicht-Metadaten
    vollstaendig) liefert `valide=True` und eine leere
    `verletzte_regeln`-Liste."""
    source_id = _fred_source_id(session)

    ergebnis = validate_bronze_kandidat(
        session,
        data_source_id=source_id,
        source_event_id="fred:CPIAUCSL:2026-01-01",
        payload={"value": "3.1"},
        beobachtungs_zeitpunkt=datetime(2026, 1, 1, tzinfo=UTC),
        anlageklassen_tag=3,
    )

    assert ergebnis.valide is True
    assert ergebnis.verletzte_regeln == ()
    assert ergebnis.event_id == "fred:CPIAUCSL:2026-01-01"


def test_missing_anlageklassen_tag_is_still_valid(session: Session) -> None:
    """@trace datenqualitaet#AC7 — `anlageklassen_tag` ist laut
    data-model.md §2 physisch nullable und daher NICHT Teil der
    Pflicht-Metadaten-Vollstaendigkeit; ein Kandidat ohne diesen Tag bleibt
    valide."""
    source_id = _fred_source_id(session)

    ergebnis = validate_bronze_kandidat(
        session,
        data_source_id=source_id,
        source_event_id="fred:CPIAUCSL:2026-01-01",
        payload={"value": "3.1"},
        beobachtungs_zeitpunkt=datetime(2026, 1, 1, tzinfo=UTC),
        anlageklassen_tag=None,
    )

    assert ergebnis.valide is True
    assert ergebnis.verletzte_regeln == ()


def test_missing_quelle_is_marked_invalid(session: Session) -> None:
    """@trace datenqualitaet#AC7 — fehlende Pflicht-Metadaten (`quelle`)
    machen einen Kandidaten ungueltig."""
    ergebnis = validate_bronze_kandidat(
        session,
        data_source_id=None,
        source_event_id="evt-1",
        payload={"value": "1"},
        beobachtungs_zeitpunkt=datetime(2026, 1, 1, tzinfo=UTC),
    )

    assert ergebnis.valide is False
    assert REGEL_QUELLE_FEHLT in ergebnis.verletzte_regeln


def test_missing_event_id_is_marked_invalid(session: Session) -> None:
    """@trace datenqualitaet#AC7 — fehlende Pflicht-Metadaten (`event_id`,
    auch als leerer/nur-Whitespace-String) machen einen Kandidaten
    ungueltig."""
    source_id = _fred_source_id(session)

    ergebnis_none = validate_bronze_kandidat(
        session,
        data_source_id=source_id,
        source_event_id=None,
        payload={"value": "1"},
        beobachtungs_zeitpunkt=datetime(2026, 1, 1, tzinfo=UTC),
    )
    ergebnis_leer = validate_bronze_kandidat(
        session,
        data_source_id=source_id,
        source_event_id="   ",
        payload={"value": "1"},
        beobachtungs_zeitpunkt=datetime(2026, 1, 1, tzinfo=UTC),
    )

    assert ergebnis_none.valide is False
    assert REGEL_EVENT_ID_FEHLT in ergebnis_none.verletzte_regeln
    assert ergebnis_leer.valide is False
    assert REGEL_EVENT_ID_FEHLT in ergebnis_leer.verletzte_regeln


def test_missing_beobachtungs_zeitpunkt_is_marked_invalid(session: Session) -> None:
    """@trace datenqualitaet#AC7 — fehlende Pflicht-Metadaten
    (`beobachtungs_zeitpunkt`) machen einen Kandidaten ungueltig."""
    source_id = _fred_source_id(session)

    ergebnis = validate_bronze_kandidat(
        session,
        data_source_id=source_id,
        source_event_id="evt-1",
        payload={"value": "1"},
        beobachtungs_zeitpunkt=None,
    )

    assert ergebnis.valide is False
    assert REGEL_BEOBACHTUNGS_ZEITPUNKT_FEHLT in ergebnis.verletzte_regeln


def test_wrong_type_beobachtungs_zeitpunkt_is_marked_invalid(session: Session) -> None:
    """@trace datenqualitaet#AC7 — Schema/Feldtyp-Regel: ein
    `beobachtungs_zeitpunkt`, der kein `datetime` ist, macht den
    Kandidaten ungueltig."""
    source_id = _fred_source_id(session)

    ergebnis = validate_bronze_kandidat(
        session,
        data_source_id=source_id,
        source_event_id="evt-1",
        payload={"value": "1"},
        beobachtungs_zeitpunkt="2026-01-01",  # type: ignore[arg-type]
    )

    assert ergebnis.valide is False
    assert REGEL_BEOBACHTUNGS_ZEITPUNKT_FALSCHER_TYP in ergebnis.verletzte_regeln


def test_missing_payload_is_marked_invalid(session: Session) -> None:
    """@trace datenqualitaet#AC7 — fehlender Rohwert (`payload`) macht den
    Kandidaten ungueltig."""
    source_id = _fred_source_id(session)

    ergebnis = validate_bronze_kandidat(
        session,
        data_source_id=source_id,
        source_event_id="evt-1",
        payload=None,
        beobachtungs_zeitpunkt=datetime(2026, 1, 1, tzinfo=UTC),
    )

    assert ergebnis.valide is False
    assert REGEL_ROH_WERT_FEHLT in ergebnis.verletzte_regeln


@pytest.mark.parametrize("ausserhalb_wert", [0, 12, -1, 100])
def test_anlageklassen_tag_out_of_range_is_marked_invalid(
    session: Session, ausserhalb_wert: int
) -> None:
    """@trace datenqualitaet#AC7 — erlaubter Wertebereich: `anlageklassen_tag`
    ausserhalb 1..11 macht den Kandidaten ungueltig."""
    source_id = _fred_source_id(session)

    ergebnis = validate_bronze_kandidat(
        session,
        data_source_id=source_id,
        source_event_id="evt-1",
        payload={"value": "1"},
        beobachtungs_zeitpunkt=datetime(2026, 1, 1, tzinfo=UTC),
        anlageklassen_tag=ausserhalb_wert,
    )

    assert ergebnis.valide is False
    assert REGEL_ANLAGEKLASSEN_TAG_AUSSERHALB_WERTEBEREICH in ergebnis.verletzte_regeln


def test_anlageklassen_tag_wrong_type_is_marked_invalid(session: Session) -> None:
    """@trace datenqualitaet#AC7 — Schema/Feldtyp-Regel: ein
    `anlageklassen_tag`, der kein `int` ist, macht den Kandidaten
    ungueltig."""
    source_id = _fred_source_id(session)

    ergebnis = validate_bronze_kandidat(
        session,
        data_source_id=source_id,
        source_event_id="evt-1",
        payload={"value": "1"},
        beobachtungs_zeitpunkt=datetime(2026, 1, 1, tzinfo=UTC),
        anlageklassen_tag="3",  # type: ignore[arg-type]
    )

    assert ergebnis.valide is False
    assert REGEL_ANLAGEKLASSEN_TAG_FALSCHER_TYP in ergebnis.verletzte_regeln


def test_multiple_violations_are_all_listed(session: Session) -> None:
    """@trace datenqualitaet#AC7 — mehrere gleichzeitig verletzte Regeln
    erscheinen alle in `verletzte_regeln` (kein Short-Circuit auf die
    erste)."""
    ergebnis = validate_bronze_kandidat(
        session,
        data_source_id=None,
        source_event_id=None,
        payload=None,
        beobachtungs_zeitpunkt=None,
    )

    assert ergebnis.valide is False
    assert REGEL_QUELLE_FEHLT in ergebnis.verletzte_regeln
    assert REGEL_EVENT_ID_FEHLT in ergebnis.verletzte_regeln
    assert REGEL_BEOBACHTUNGS_ZEITPUNKT_FEHLT in ergebnis.verletzte_regeln
    assert REGEL_ROH_WERT_FEHLT in ergebnis.verletzte_regeln


def test_invalid_candidate_is_logged_with_reason(
    session: Session, caplog: pytest.LogCaptureFixture
) -> None:
    """@trace datenqualitaet#AC8 — ein ungueltiger Kandidat wird nicht nur
    markiert, sondern MIT GRUND protokolliert (deckt E1)."""
    source_id = _fred_source_id(session)

    with caplog.at_level(logging.WARNING, logger="app.db.validation"):
        ergebnis = validate_bronze_kandidat(
            session,
            data_source_id=source_id,
            source_event_id="evt-1",
            payload=None,
            beobachtungs_zeitpunkt=datetime(2026, 1, 1, tzinfo=UTC),
        )

    assert ergebnis.valide is False
    warnungen = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert len(warnungen) == 1
    assert REGEL_ROH_WERT_FEHLT in warnungen[0].getMessage()
    assert "evt-1" in warnungen[0].getMessage()


def test_valid_candidate_logs_nothing(session: Session, caplog: pytest.LogCaptureFixture) -> None:
    """@trace datenqualitaet#AC8 — ein gueltiger Kandidat loest KEIN
    Warn-Log aus (nur ungueltige Kandidaten werden protokolliert)."""
    source_id = _fred_source_id(session)

    with caplog.at_level(logging.WARNING, logger="app.db.validation"):
        ergebnis = validate_bronze_kandidat(
            session,
            data_source_id=source_id,
            source_event_id="evt-1",
            payload={"value": "1"},
            beobachtungs_zeitpunkt=datetime(2026, 1, 1, tzinfo=UTC),
        )

    assert ergebnis.valide is True
    assert [r for r in caplog.records if r.levelno == logging.WARNING] == []


def test_event_id_collision_with_different_observed_at_is_invalid(session: Session) -> None:
    """@trace datenqualitaet#AC7,AC8 — Edge-Case (Spec
    Edge-Cases-Abschnitt, S-022-Handoff): trifft fuer eine bereits
    bekannte Ereignis-Identitaet ein Kandidat mit ABWEICHENDEM
    `beobachtungs_zeitpunkt` ein, ist das keine Revision derselben
    Beobachtung, sondern eine wiederverwendete Event-ID -> Validierungsfehler."""
    source_id = _fred_source_id(session)
    record_observation(
        session,
        data_source_id=source_id,
        source_event_id="fred:CPIAUCSL:2026-01-01",
        payload={"value": "3.1"},
        beobachtungs_zeitpunkt=datetime(2026, 1, 1, tzinfo=UTC),
    )
    session.commit()

    ergebnis = validate_bronze_kandidat(
        session,
        data_source_id=source_id,
        source_event_id="fred:CPIAUCSL:2026-01-01",
        payload={"value": "9.9"},
        # Abweichender beobachtungs_zeitpunkt -> andere Beobachtung, nicht
        # dieselbe revidiert (Unterscheidung zu AC10/A1).
        beobachtungs_zeitpunkt=datetime(2026, 2, 1, tzinfo=UTC),
    )

    assert ergebnis.valide is False
    assert REGEL_EVENT_ID_KOLLISION in ergebnis.verletzte_regeln


def test_legit_revision_same_observed_at_is_not_flagged_as_collision(session: Session) -> None:
    """@trace datenqualitaet#AC7,AC8 — eine legitime Revision (AC10/A1,
    z.B. FRED-Korrektur: gleicher `beobachtungs_zeitpunkt`, neuer Wert)
    wird NICHT als Event-ID-Kollision markiert."""
    source_id = _fred_source_id(session)
    beobachtet = datetime(2026, 1, 1, tzinfo=UTC)
    record_observation(
        session,
        data_source_id=source_id,
        source_event_id="fred:CPIAUCSL:2026-01-01",
        payload={"value": "3.1"},
        beobachtungs_zeitpunkt=beobachtet,
    )
    session.commit()

    ergebnis = validate_bronze_kandidat(
        session,
        data_source_id=source_id,
        source_event_id="fred:CPIAUCSL:2026-01-01",
        payload={"value": "3.4"},  # rueckwirkend korrigierter Wert
        beobachtungs_zeitpunkt=beobachtet,  # gleiche Beobachtung
    )

    assert ergebnis.valide is True
    assert REGEL_EVENT_ID_KOLLISION not in ergebnis.verletzte_regeln


def test_first_observation_never_flagged_as_collision(session: Session) -> None:
    """@trace datenqualitaet#AC7 — der allererste Kandidat einer
    Ereignis-Identitaet hat keine Vorgaenger-Zeile und kann daher nie als
    Event-ID-Kollision markiert werden."""
    source_id = _fred_source_id(session)

    ergebnis = validate_bronze_kandidat(
        session,
        data_source_id=source_id,
        source_event_id="fred:CPIAUCSL:2026-03-01",
        payload={"value": "1.0"},
        beobachtungs_zeitpunkt=datetime(2026, 3, 1, tzinfo=UTC),
    )

    assert ergebnis.valide is True
    assert session.query(MarketDataBronze).count() == 0
