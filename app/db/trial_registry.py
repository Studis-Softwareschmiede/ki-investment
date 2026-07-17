"""Trial-Registry-Store — append-only Zählung ALLER an das Validierungs-Gate
übergebenen Regelvarianten (Story S-059, Spec `docs/specs/lernschleife.md`
AC3, → BR-118).

AC3 ("Jede an das Gate übergebene Regelvariante wird in einer
Trial-Registry gezählt — auch verworfene; ohne diese Zählung ist die
Deflated Sharpe Ratio ungültig. Abgelehnte Regeln werden archiviert, nie
gelöscht"): dieses Modul bietet ausschliesslich `registriere_trial()`
(Insert), `archiviere_trial()` (UPDATE — ausschliesslich der `archived`-
Spalte, Ablehnung) sowie die Lesefunktionen `anzahl_trials()`/
`trials_fuer_hypothese()` — keine Delete-Funktion existiert. Die Migration
(`app.db.models.TrialRegistry`) sichert dieselbe Invariante zusätzlich
DB-seitig per BEFORE-DELETE-Trigger unter Postgres (zweite Ebene, analog
BR-115/`transaction`).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import TrialRegistry


def registriere_trial(
    session: Session,
    *,
    hypothesis_id: uuid.UUID,
    variant_hash: str,
    params: dict[str, Any],
    getestet_am: datetime | None = None,
) -> TrialRegistry:
    """Zählt eine an das Gate übergebene Regelvariante (AC3) — ein reiner
    Insert. `getestet_am` ist injizierbar (Default: jetzt) für
    deterministische Tests, analog `ingest_dead_letter.record_dead_letter`.
    """
    eintrag = TrialRegistry(
        id=uuid.uuid4(),
        hypothesis_id=hypothesis_id,
        variant_hash=variant_hash,
        params=params,
        archived=False,
        tested_at=getestet_am or datetime.now(UTC),
    )
    session.add(eintrag)
    session.commit()
    return eintrag


def archiviere_trial(session: Session, *, trial_id: uuid.UUID) -> TrialRegistry:
    """Markiert eine bereits registrierte Variante als abgelehnt/archiviert
    (AC3 „Abgelehnte Regeln werden archiviert, nie gelöscht") — setzt
    ausschliesslich `archived=True`, die Zeile selbst bleibt unverändert
    bestehen (kein DELETE, kein Überschreiben der übrigen Felder)."""
    eintrag = session.get(TrialRegistry, trial_id)
    if eintrag is None:
        raise ValueError(f"trial_registry-Eintrag {trial_id} existiert nicht")
    eintrag.archived = True
    session.commit()
    return eintrag


def anzahl_trials(session: Session, *, hypothesis_id: uuid.UUID) -> int:
    """Zählt ALLE je registrierten Varianten einer Hypothese (AC3-Kernzweck:
    „wird ... gezählt" — Basis der Deflated-Sharpe-Ratio-Korrektur, AC7,
    Folge-Story) — inklusive archivierter/verworfener Varianten."""
    return session.execute(
        select(func.count())
        .select_from(TrialRegistry)
        .where(TrialRegistry.hypothesis_id == hypothesis_id)
    ).scalar_one()


def trials_fuer_hypothese(session: Session, *, hypothesis_id: uuid.UUID) -> list[TrialRegistry]:
    """Liest alle registrierten Varianten einer Hypothese (älteste zuerst),
    inklusive archivierter — vollständige Historie für Audit/DSR."""
    return list(
        session.execute(
            select(TrialRegistry)
            .where(TrialRegistry.hypothesis_id == hypothesis_id)
            .order_by(TrialRegistry.tested_at.asc())
        )
        .scalars()
        .all()
    )


__all__ = [
    "registriere_trial",
    "archiviere_trial",
    "anzahl_trials",
    "trials_fuer_hypothese",
]
