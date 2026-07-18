"""Gate-Ergebnis-Store — Persistenz der Ampel-Entscheidung je Gate-Auswertung
(Story S-062, Spec `docs/specs/lernschleife.md` AC10/AC11/AC12, →
BR-119/BR-120).

`app.contracts.lernschleife` (S-061) hat die Persistenz von `ampel` +
`psr`/`min_trl` bewusst dieser Story überlassen: „dieses Feld gehört zu
`gate_result` (`docs/data-model.md` §6), dessen Persistenz ... laut
Ampel-Umsetzung (AC10/AC11) weiterhin S-062-Scope ist". `registriere_
gate_ergebnis` schreibt EINE Zeile je Gate-Auswertung (nach Stufe A oder
nach Stufe B) — die Ampel selbst wird vom reinen Domain-Kern
`app.domain.lernschleife.gate.leite_ampel_ab` abgeleitet (P1, kein
DB-Zugriff); dieses Modul konsumiert nur das bereits abgeleitete Ergebnis.

NFR „Nachvollziehbarkeit" (Spec): jede Ampel-Entscheidung trägt ihre
Metriken (`sample_size`/`wfe`/`dsr` aus Stufe A, `psr`/`min_trl` aus Stufe
B, falls vorhanden) und eine `begruendung` — `gate_ergebnisse_fuer_trial`
liest die vollständige Audit-Historie eines Trials.
"""

from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Literal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.contracts.kandidatensuche import Ampel
from app.contracts.lernschleife import StufeAReport, StufeBReport
from app.db.models import GateResult

_SEKUNDEN_PRO_TAG = Decimal(86400)


def registriere_gate_ergebnis(
    session: Session,
    *,
    trial_id: uuid.UUID,
    ampel: Ampel,
    stufe_a_report: StufeAReport,
    stufe_b_report: StufeBReport | None = None,
) -> GateResult:
    """AC10/AC11 — persistiert EINE Gate-Auswertung: `stufe` ist
    `"B_paper"`, sobald ein `stufe_b_report` vorliegt (sonst
    `"A_historisch"`); `psr`/`min_trl` bleiben `NULL`, solange Stufe B noch
    nicht gelaufen ist (→ BR-120, „bei jeder [Stufe-B-]Auswertung"). Der
    Aufrufer leitet `ampel` vorher über
    `app.domain.lernschleife.gate.leite_ampel_ab` ab — dieses Modul
    berechnet die Ampel selbst nicht (P1-Trennung Domain/DB)."""
    stufe: Literal["A_historisch", "B_paper"] = (
        "B_paper" if stufe_b_report is not None else "A_historisch"
    )
    min_trl: Decimal | None = None
    if stufe_b_report is not None and stufe_b_report.mintrl_restlaufzeit is not None:
        min_trl = Decimal(stufe_b_report.mintrl_restlaufzeit.total_seconds()) / _SEKUNDEN_PRO_TAG
    begruendung = (
        stufe_b_report.begruendung if stufe_b_report is not None else stufe_a_report.begruendung
    )

    eintrag = GateResult(
        id=uuid.uuid4(),
        trial_id=trial_id,
        stufe=stufe,
        ampel=ampel,
        sample_size=stufe_a_report.n_trades,
        wfe=stufe_a_report.walk_forward_effizienz,
        dsr=stufe_a_report.dsr,
        psr=stufe_b_report.psr if stufe_b_report is not None else None,
        min_trl=min_trl,
        begruendung=begruendung,
    )
    session.add(eintrag)
    session.commit()
    return eintrag


def gate_ergebnisse_fuer_trial(session: Session, *, trial_id: uuid.UUID) -> list[GateResult]:
    """Liest alle Gate-Auswertungen eines Trials (älteste zuerst) — volle
    Audit-Historie (NFR „Nachvollziehbarkeit")."""
    return list(
        session.execute(
            select(GateResult)
            .where(GateResult.trial_id == trial_id)
            .order_by(GateResult.created_at.asc())
        )
        .scalars()
        .all()
    )


__all__ = ["registriere_gate_ergebnis", "gate_ergebnisse_fuer_trial"]
