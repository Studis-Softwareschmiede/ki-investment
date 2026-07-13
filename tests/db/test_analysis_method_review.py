"""Tests fuer den quartalsweisen Review-Hinweis `app/db/analysis_method_review.py` (Story S-018).

Covers (anlageklassen-config): AC11

Deckt AC11 ("Das System weist quartalsweise auf die fällige Überprüfung der
Rankings hin — Erinnerung/Kennzeichnung des Review-Bedarfs, ohne
Ranking-Werte automatisch zu verändern"): `ist_review_faellig` als reine
Berechnung sowie `methoden_mit_faelligem_review` als Lesefunktion über die
AKTUELL gültige `analysis_method`-Version. Beide Funktionen ändern
nachweislich keine Werte (Nicht-Ziel der Spec: kein automatisches Anpassen
von Rankings) — dies wird explizit durch einen Vorher/Nachher-Vergleich des
`ranking`-Werts geprüft, nicht nur durch Abwesenheit einer Schreiboperation
im Code.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.db.analysis_method_review import (
    REVIEW_INTERVALL,
    ist_review_faellig,
    methoden_mit_faelligem_review,
)
from app.db.base import Base
from app.db.models import AnalysisCategory, AnalysisMethod, AnalysisMethodVersion, AssetClass

JETZT = datetime(2026, 7, 13, tzinfo=UTC)


def test_ist_review_faellig_true_when_interval_exceeded() -> None:
    """@trace anlageklassen-config#AC11 — ein Review, das länger als ein
    Quartal zurückliegt, gilt als fällig."""
    letztes_review = JETZT - REVIEW_INTERVALL - timedelta(days=1)
    assert ist_review_faellig(letztes_review, jetzt=JETZT) is True


def test_ist_review_faellig_false_within_interval() -> None:
    """@trace anlageklassen-config#AC11 — innerhalb des Quartals ist kein
    Review fällig."""
    letztes_review = JETZT - timedelta(days=30)
    assert ist_review_faellig(letztes_review, jetzt=JETZT) is False


def test_ist_review_faellig_true_exactly_at_boundary() -> None:
    """@trace anlageklassen-config#AC11 — genau am Intervall-Rand gilt der
    Review bereits als fällig (`>=`, kein Off-by-one-Fenster)."""
    letztes_review = JETZT - REVIEW_INTERVALL
    assert ist_review_faellig(letztes_review, jetzt=JETZT) is True


def _engine_mit_methode(
    *, last_reviewed_at: datetime, is_current: bool = True
) -> tuple[Session, AnalysisMethod]:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = Session(engine)
    session.add(AssetClass(id=1, name="Aktien", prio_stufe="MVP", aktiv=True, retail_driven=True))
    session.add(AnalysisCategory(code="fundamental", name="Fundamental", ist_risiko=False))
    version = AnalysisMethodVersion(is_current=is_current)
    session.add(version)
    session.commit()

    methode = AnalysisMethod(
        asset_class_id=1,
        category_code="fundamental",
        config_version_id=version.id,
        code="F1",
        kurzbezeichnung="DCF",
        ranking=9,
        last_reviewed_at=last_reviewed_at,
    )
    session.add(methode)
    session.commit()
    return session, methode


def test_methoden_mit_faelligem_review_finds_overdue_method() -> None:
    """@trace anlageklassen-config#AC11 — eine Methode mit überfälligem
    Review taucht in der Fälligkeits-Liste auf."""
    ueberfaellig_seit = JETZT - REVIEW_INTERVALL - timedelta(days=5)
    session, _methode = _engine_mit_methode(last_reviewed_at=ueberfaellig_seit)
    faellige = methoden_mit_faelligem_review(session, jetzt=JETZT)
    assert [m.code for m in faellige] == ["F1"]


def test_methoden_mit_faelligem_review_excludes_recently_reviewed() -> None:
    """@trace anlageklassen-config#AC11 — eine kürzlich geprüfte Methode
    (innerhalb des Quartals) taucht NICHT in der Fälligkeits-Liste auf."""
    session, _ = _engine_mit_methode(last_reviewed_at=JETZT - timedelta(days=10))
    faellige = methoden_mit_faelligem_review(session, jetzt=JETZT)
    assert faellige == []


def test_methoden_mit_faelligem_review_ignores_non_current_version() -> None:
    """@trace anlageklassen-config#AC11 — eine überfällige Methode einer
    NICHT mehr aktuellen Version wird nicht als fällig gemeldet (Review
    betrifft die aktive Methodentabelle, nicht die Historie)."""
    session, _ = _engine_mit_methode(
        last_reviewed_at=JETZT - REVIEW_INTERVALL - timedelta(days=5), is_current=False
    )
    faellige = methoden_mit_faelligem_review(session, jetzt=JETZT)
    assert faellige == []


def test_review_hint_does_not_change_ranking_value() -> None:
    """@trace anlageklassen-config#AC11 — die Fälligkeitsprüfung ist eine
    reine Lesefunktion: das `ranking` bleibt vor und nach dem Aufruf
    identisch (kein automatisches Anpassen, Spec-Nicht-Ziel)."""
    session, methode = _engine_mit_methode(
        last_reviewed_at=JETZT - REVIEW_INTERVALL - timedelta(days=5)
    )
    ranking_vorher = methode.ranking

    methoden_mit_faelligem_review(session, jetzt=JETZT)

    session.refresh(methode)
    assert methode.ranking == ranking_vorher == 9
