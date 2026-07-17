"""Research — Hypothesen-Erzeugung (Story S-058, Spec
`docs/specs/lernschleife.md` AC1/AC2).

Reiner Domain-Kern (architecture.md §4 P1): kein I/O, keine DB, kein LLM.
Die Muster-Erkennung selbst (Vergleich Tagesgewinner/-verlierer gegen die
aktuell aktiven Suchkriteria, `[[datenquellen-abfrage]]`) liegt ausserhalb
dieser Story — `erzeuge_hypothesen` konsumiert bereits identifizierte
`Musterbeobachtung`-Objekte (Aufrufer/Orchestration-Schicht).

- **AC1 (Mindest-Evidenz-Protokoll, "ändert die Suchkriterien niemals
  direkt"):** `erzeuge_hypothesen` nimmt keine Suchkriteria-Referenz
  entgegen und gibt keine zurück — sie kann die Suchkriteria strukturell
  nicht mutieren. Jede erzeugte `Hypothese` trägt ihr vollständiges
  `Evidenzprotokoll` unverändert aus der `Musterbeobachtung` (bereits
  durch den Pydantic-Vertrag erzwungen, siehe `app.contracts.research`).
- **AC2 (Marktlogik-Filter):** eine `Musterbeobachtung` ohne marktlogische
  Begründung (`marktlogik` ist `None` oder nur Leerraum) wird NICHT als
  Hypothese weitergegeben — stilles Verwerfen, kein Fehler (rein
  statistische Zufallsmuster sind kein Programmierfehler des Aufrufers).
"""

from __future__ import annotations

import uuid
from collections.abc import Sequence

from app.contracts.research import Hypothese, Musterbeobachtung


def erzeuge_hypothesen(musterbeobachtungen: Sequence[Musterbeobachtung]) -> list[Hypothese]:
    """AC1/AC2 — wandelt beobachtete Muster in Hypothesen für das
    Validierungs-Gate um (Main Success Scenario Schritt 2). Muster ohne
    marktlogische Begründung werden verworfen (AC2); alle übrigen werden
    unverändert samt ihrem Mindest-Evidenz-Protokoll zu einer `Hypothese`
    (AC1), mit einer frisch vergebenen `hypothese_id`. Die Reihenfolge der
    Eingabe bleibt erhalten."""
    hypothesen: list[Hypothese] = []
    for beobachtung in musterbeobachtungen:
        marktlogik = (beobachtung.marktlogik or "").strip()
        if not marktlogik:
            continue
        hypothesen.append(
            Hypothese(
                hypothese_id=uuid.uuid4(),
                beschreibung=beobachtung.beschreibung,
                marktlogik=marktlogik,
                evidenz=beobachtung.evidenz,
            )
        )
    return hypothesen


__all__ = ["erzeuge_hypothesen"]
