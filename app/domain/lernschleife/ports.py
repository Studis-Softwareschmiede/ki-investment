"""Repository-Port für den Lesezugriff auf persistierte Gate-Ergebnisse
(architecture.md §4 "abstrakte Protokolle in `app/domain/**/ports.py`", P1;
analog `app.domain.portfolio.ports.PositionRepository`).

Der reine Domain-Kern (`app.domain.lernschleife.gate.leite_ampel_ab`) bleibt
unverändert frei von DB-Zugriff (P1) — dieser Port dient AUSSCHLIESSLICH dem
Lese-Zugriff der Anzeige-Schicht (Betriebs-Cockpit System-Status,
`docs/specs/frontend-cockpit.md` AC8, Story S-068, → BR-025) auf die
zuletzt persistierte Gate-Auswertung (`app.db.models.GateResult`, S-062).
Die konkrete Implementierung liegt im Adapter `app.adapters.repositories
.gate_result_repository.SqlAlchemyGateErgebnisRepository`; die Schreibseite
(`app.db.gate_result.registriere_gate_ergebnis`, S-062) bleibt unverändert
— dieser Port ergänzt nur einen zusätzlichen Lese-Pfad "neueste Auswertung
über ALLE Trials hinweg" (bislang existierte nur `gate_ergebnisse_fuer_trial`,
das bereits eine bekannte `trial_id` voraussetzt)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

from app.contracts.kandidatensuche import Ampel


@dataclass(frozen=True)
class LetztesGateErgebnis:
    """Schreibgeschützte Sicht auf die zuletzt persistierte Gate-Auswertung
    — nur die für die System-Status-Ampel (AC8) benötigten Felder (nicht
    der volle `GateResult`-Datensatz inkl. Metriken/Begründung — das ist
    Kandidaten-/Trial-Detail-Scope, kein Cockpit-System-Status-Scope)."""

    ampel: Ampel
    ermittelt_am: datetime


class GateErgebnisRepository(Protocol):
    """Lese-Zugriff auf die zuletzt persistierte Gate-Auswertung."""

    def letztes_ergebnis(self) -> LetztesGateErgebnis | None:
        """Liefert die neueste Gate-Auswertung über ALLE Trials hinweg
        (`GateResult.created_at` absteigend, erste Zeile) oder `None`, falls
        noch keine Gate-Auswertung vorliegt (Cold-Start, kein Trial
        ausgewertet — deckungsgleich mit dem AC4/A3-"kein Urteil"-Fall, für
        den `app.domain.lernschleife.gate.leite_ampel_ab` ohnehin nie einen
        `GateResult` persistieren lässt, siehe `app.db.gate_result`-
        Docstring: nur 🟢/🟡/🔴 werden gespeichert)."""
        ...
