"""Modul-Verträge Research — Hypothesen-Erzeugung mit Mindest-Evidenz-
Protokoll & Marktlogik-Filter (Story S-058, Spec `docs/specs/lernschleife.md`
AC1/AC2, → `docs/data-model.md` §6 `rule_hypothesis`).

architecture.md §2 P2 ("Explizite Modul-Verträge"): jeder Modul-Übergang
läuft über ein typisiertes DTO in `app/contracts/`. Dieses Modul bildet
den Verträge-Abschnitt der Spec ab:

- **`Evidenzprotokoll`** — das von AC1 geforderte Mindest-Evidenz-Protokoll
  einer Hypothese: "mindestens Anzahl Fälle, Zeitraum, Signalquelle/
  Anlageklasse". Alle vier Angaben sind Pflichtfelder — eine Hypothese
  ohne vollständiges Protokoll kann mit diesem Vertrag strukturell gar
  nicht gebildet werden.
- **`Musterbeobachtung`** — Research-Input (Verträge "Research-Input":
  Tagesgewinner/-verlierer + optional aktive Suchkriteria; Main Success
  Scenario Schritt 1): ein von Research beobachtetes Muster, VOR der
  AC1/AC2-Prüfung. `marktlogik` ist bewusst optional (`None`/leer möglich)
  — genau das ist der AC2-Fall ("rein statistische Zufallsmuster ohne
  marktlogische Begründung"), der von
  `app.domain.research.hypothesen_erzeugung.erzeuge_hypothesen` verworfen
  wird (keine Hypothese, kein Fehler).
- **`Hypothese`** — Spec-Vertrag "Hypothese (Research → Gate):
  `{ hypothese_id, beschreibung, marktlogik, evidenz{...} }`". Wird
  AUSSCHLIESSLICH von `erzeuge_hypothesen` gebaut, nie direkt aus einer
  `Musterbeobachtung` — die Existenz eines `Hypothese`-Objekts ist damit
  selbst der Beleg, dass beide AC1/AC2-Prüfungen bestanden wurden.

**Bewusst NICHT Teil dieser Story:** die eigentliche Muster-Erkennung
(Vergleich Tagesgewinner/-verlierer gegen aktuelle Suchkriteria, LLM-
gestützte Musterbeschreibung) — `Musterbeobachtung` ist bereits das
Ergebnis dieses (ausserhalb dieser Story liegenden) Schritts; ebenso
`Trial-Registry`/Gate-Anbindung (AC3+, S-059/S-060/S-061/S-062, kein
Gold-Plating über AC1/AC2 hinaus)."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, model_validator


class Evidenzprotokoll(BaseModel):
    """Mindest-Evidenz-Protokoll (AC1): Anzahl Fälle, Zeitraum,
    Signalquelle/Anlageklasse — die von der Spec explizit genannten
    Mindestangaben. `anzahl_faelle` muss positiv sein (0 Fälle sind keine
    Evidenz); `zeitraum_bis` darf `zeitraum_von` nicht vorausgehen."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    anzahl_faelle: int = Field(gt=0)
    zeitraum_von: datetime
    zeitraum_bis: datetime
    signalquelle: str = Field(min_length=1)
    anlageklasse: int = Field(ge=1, le=11)

    @model_validator(mode="after")
    def _zeitraum_konsistent(self) -> "Evidenzprotokoll":
        if self.zeitraum_bis < self.zeitraum_von:
            raise ValueError("zeitraum_bis darf nicht vor zeitraum_von liegen")
        return self


class Musterbeobachtung(BaseModel):
    """Ein von Research beobachtetes Muster (Main Success Scenario
    Schritt 1) — VOR der AC1/AC2-Prüfung. `marktlogik` ist optional/leer,
    wenn Research (noch) keine marktlogische Erklärung für das Muster
    gefunden hat (AC2: führt zur Verwerfung, kein Hypothese-Output)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    beschreibung: str = Field(min_length=1)
    marktlogik: str | None = None
    evidenz: Evidenzprotokoll


class Hypothese(BaseModel):
    """Hypothese (Research → Gate) — Spec-Vertrag `{ hypothese_id,
    beschreibung, marktlogik, evidenz }` (AC1). Wird ausschliesslich von
    `app.domain.research.hypothesen_erzeugung.erzeuge_hypothesen` gebaut."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    hypothese_id: uuid.UUID
    beschreibung: str
    marktlogik: str = Field(min_length=1)
    evidenz: Evidenzprotokoll


__all__ = [
    "Evidenzprotokoll",
    "Hypothese",
    "Musterbeobachtung",
]
