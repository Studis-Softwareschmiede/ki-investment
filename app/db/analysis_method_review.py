"""Quartalsweiser Review-Hinweis für Methodentabellen-Rankings (AC11, BR-132).

Reiner Prozess-Hinweis (Erinnerung/Kennzeichnung des Review-Bedarfs) — kein
automatisches Ändern von Ranking-Werten (Spec-Nicht-Ziel
`docs/specs/anlageklassen-config.md`: "Kein automatisches Anpassen von
Rankings/Gewichten"). `REVIEW_INTERVALL` nähert "quartalsweise" als 90 Tage
an (kalendarisch ~1 Quartal); ein tatsächliches Review aktualisiert
ausschliesslich `AnalysisMethod.last_reviewed_at`, niemals `ranking` selbst.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import AnalysisMethod, AnalysisMethodVersion

# ~1 Quartal (BR-132). Bewusst ein fixer Tage-Wert statt Kalendermonate —
# reiner Prozess-Hinweis, keine buchhalterische Stichtagslogik nötig.
REVIEW_INTERVALL = timedelta(days=90)


def ist_review_faellig(letztes_review: datetime, jetzt: datetime | None = None) -> bool:
    """@Doku AC11 — True, wenn seit `letztes_review` mindestens ein Quartal
    (`REVIEW_INTERVALL`) vergangen ist. Reine Berechnung, ändert nichts."""
    referenz = jetzt if jetzt is not None else datetime.now(UTC)
    return (referenz - letztes_review) >= REVIEW_INTERVALL


def methoden_mit_faelligem_review(
    session: Session, jetzt: datetime | None = None
) -> list[AnalysisMethod]:
    """Liefert alle Methoden der AKTUELL gültigen `analysis_method`-Version,
    deren Ranking-Review fällig ist (AC11) — reine Lesefunktion, verändert
    keine Werte (kein automatisches Ranking-Update)."""
    referenz = jetzt if jetzt is not None else datetime.now(UTC)
    grenze = referenz - REVIEW_INTERVALL
    zeilen = (
        session.execute(
            select(AnalysisMethod)
            .join(
                AnalysisMethodVersion,
                AnalysisMethod.config_version_id == AnalysisMethodVersion.id,
            )
            .where(AnalysisMethodVersion.is_current.is_(True))
            .where(AnalysisMethod.last_reviewed_at <= grenze)
        )
        .scalars()
        .all()
    )
    return list(zeilen)
