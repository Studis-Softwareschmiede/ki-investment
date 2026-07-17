"""Tests für `app.db.rule_hypothesis` (Story S-058).

Covers (lernschleife): AC1, AC2

AC1/AC2: `speichere_hypothese()` persistiert eine bereits AC1/AC2-geprüfte
`Hypothese` (Pydantic-Vertrag `app.contracts.research.Hypothese`) als
`rule_hypothesis`-Zeile — dieses Modul führt selbst keine fachliche
Prüfung mehr durch (das leistet `app.domain.research.hypothesen_erzeugung.
erzeuge_hypothesen`, siehe `tests/domain/research/`), sondern belegt hier
nur, dass das vollständige Evidenzprotokoll + `marktlogik` unverändert in
die DB-Zeile übernommen werden.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.contracts.research import Evidenzprotokoll, Hypothese
from app.db.base import Base
from app.db.rule_hypothesis import speichere_hypothese


def _session() -> Session:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return Session(engine)


def _hypothese(**overrides: object) -> Hypothese:
    evidenz = Evidenzprotokoll(
        anzahl_faelle=42,
        zeitraum_von=datetime(2026, 1, 1, tzinfo=UTC),
        zeitraum_bis=datetime(2026, 6, 30, tzinfo=UTC),
        signalquelle="news-sentiment-feed",
        anlageklasse=1,
    )
    defaults: dict[str, object] = {
        "hypothese_id": uuid.uuid4(),
        "beschreibung": "Small-Cap-Gewinner mit ungewöhnlich hohem RVOL vor News",
        "marktlogik": "Erhöhtes Handelsvolumen vor Nachrichten deutet auf Informationsvorlauf hin.",
        "evidenz": evidenz,
    }
    defaults.update(overrides)
    return Hypothese(**defaults)  # type: ignore[arg-type]


def test_speichere_hypothese_persistiert_alle_ac1_ac2_felder() -> None:
    """@trace lernschleife#AC1,AC2 — Beschreibung, Marktlogik und das volle
    Evidenzprotokoll landen unverändert in der `rule_hypothesis`-Zeile."""
    session = _session()
    hypothese = _hypothese()

    eintrag = speichere_hypothese(
        session, hypothese=hypothese, params={"schwelle": 2}, free_param_count=1
    )

    assert eintrag.id == hypothese.hypothese_id
    assert eintrag.beschreibung == hypothese.beschreibung
    assert eintrag.marktlogik == hypothese.marktlogik
    assert eintrag.anzahl_faelle == hypothese.evidenz.anzahl_faelle
    # SQLite speichert TIMESTAMPTZ ohne Zeitzoneninfo (Test-Dialekt-
    # Eigenheit, analog `tested_at`-Konvention in test_trial_registry.py);
    # unter Postgres bleibt die Zeitzone erhalten.
    assert eintrag.zeitraum_von.replace(tzinfo=UTC) == hypothese.evidenz.zeitraum_von
    assert eintrag.zeitraum_bis.replace(tzinfo=UTC) == hypothese.evidenz.zeitraum_bis
    assert eintrag.signalquelle == hypothese.evidenz.signalquelle
    assert eintrag.asset_class_id == hypothese.evidenz.anlageklasse
    assert eintrag.params == {"schwelle": 2}
    assert eintrag.free_param_count == 1
    assert eintrag.created_at is not None


def test_speichere_hypothese_ist_je_hypothese_id_wiederauffindbar() -> None:
    """@trace lernschleife#AC1 — die Zeile ist über die von Research
    vergebene `hypothese_id` (PK) identifizierbar (Basis für die spätere
    Trial-Registry-FK-Zuordnung, AC3, Folge-Story)."""
    session = _session()
    hypothese = _hypothese()

    speichere_hypothese(session, hypothese=hypothese, params={}, free_param_count=0)

    from app.db.models import RuleHypothesis

    gefunden = session.get(RuleHypothesis, hypothese.hypothese_id)
    assert gefunden is not None
    assert gefunden.beschreibung == hypothese.beschreibung
