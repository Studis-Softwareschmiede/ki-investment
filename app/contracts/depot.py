"""Modul-Verträge Depotmodul: Fill-Input & Buchungs-Ergebnis (Modul 16,
architecture.md §2 P2, Spec `docs/specs/depot.md` "Verträge").

Bildet aus der Spec ab, soweit von dieser Story (S-015, AC1 + AC10) benötigt:

- `Richtung` — Kauf/Verkauf (Fill-Input-Vertrag).
- `ExitRegeln` — das beim Kauf fixierte Exit-Regel-Bündel (Feld
  `exit_regeln` des Fill-Inputs). Depot behandelt es als durchgereichten
  Wert und prüft nur dessen **Präsenz** bei einem Kauf (AC1) — die
  inhaltliche Vollständigkeit der einzelnen Exit-Regel-Kategorien
  (Stop-Trigger/Thesis-Invalidierung Pflicht, Time-Box optional) ist Sache
  von `strategie-exit-regeln` (eigene Spec/Story-Reihe, AC6) und wird hier
  NICHT dupliziert.
- `FillInput` — das Ausführungsergebnis vom Kauf-/Verkaufsmodul. Die
  universellen Pflichtfelder (**Client-Order-ID** — Dedup-Schlüssel, ADR-011/
  P8, nachgezogen im DBA-Zweit-Review von S-016, siehe unten —, Titel-Identität,
  Anlageklasse, GICS-Branche, Richtung, Menge, Fill-Preis, Kosten,
  Arrival-Price, Währung, Zeitstempel, **Modus** `echt`/`simuliert` —
  nachgezogen in S-016, siehe `Modus`-Docstring) sind Pydantic-Pflichtfelder
  (AC10, deckt E1: "fehlende Pflichtfelder");
  bei Kauf sind zusätzlich Strategie, Zeithorizont, Exit-Regeln und These
  Pflicht (AC1) — durchgesetzt über einen `model_validator`, NICHT über
  bedingungslos required Felder (bei Verkauf bleiben sie zulässig `None`,
  da diese Attribute bereits beim ursprünglichen Kauf fixiert wurden,
  BR-010, und beim Verkauf nicht erneut mitgeliefert werden müssen). Fehlt
  eines dieser Felder, verweigert pydantic die Instanziierung — Muster
  identisch zu `app.contracts.dateneingang.Datenpunkt` (S-005): der
  Aufrufer (`app.domain.portfolio.fill_booking.pruefe_fill`) fängt das ab
  und liefert ein strukturiertes Ablehnungs-Ergebnis statt eines Crashs.
- `FillProtokollEintrag` — auditierbarer Protokolleintrag für eine
  abgelehnte Fill-Buchung (AC1 "protokolliert" / AC10 "protokolliert").
- `FillErgebnis` — strukturiertes Ergebnis des Buchungs-Gates
  (`app.domain.portfolio.fill_booking.pruefe_fill`). Bei `status ==
  "gebucht"` trägt es das validierte `FillInput` plus die berechnete
  `resultierende_menge` — **kein** DB-Write geschieht hier (Positions-
  Fortschreibung mit Ø-Einstand/Gebühren-Netting ist
  `app.domain.portfolio.position_booking`, S-016, AC2/AC3/AC5).

Nicht Teil dieser Story (andere Storys/Nicht-Ziele):
- Keine Transaktionshistorie/TCA-Persistenz (AC4/AC7 → S-035).
- Keine Portfolio-Aggregate (AC8/AC9 → S-036).
- Keine Exit-Regel-Interpretation/-Persistenz (Stop-Trigger-Kategorien,
  ATR-Multiplikator etc. → `strategie-exit-regeln`, S-037/S-038); S-016
  legt beim ersten Kauf eines Titels nur die `position`-Zeile selbst an.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

#: Handelsrichtung des Fills (Verträge, Spec `depot`).
Richtung = Literal["kauf", "verkauf"]

#: Handelsmodus des Fills (BR-130, Mode-Isolation) — echt/simuliert werden
#: in Aggregaten nie vermischt; jede transaktionale Entität trägt diesen
#: Wert (data-model.md Präambel). War in der ursprünglichen Verträge-Liste
#: von S-015 nicht aufgeführt (Feldname-Lücke) — für S-016 nachgezogen, da
#: `position.mode` NOT NULL ist (S-016 legt hier erstmals Position-Zeilen
#: an) und der Modus ausschliesslich aus dem Ausführungsergebnis selbst
#: stammen kann (analog zu `arrival_price`/`fill_preis`), nicht aus einer
#: globalen Konfiguration.
Modus = Literal["echt", "simuliert"]

#: Gründe, aus denen ein Fill nicht gebucht wird (AC10, deckt E1).
FillAblehnungsgrund = Literal["unvollstaendig", "negative_menge"]

#: Kauf-only Pflichtfelder von `FillInput` (AC1) — Namen wie im Vertrag.
_KAUF_PFLICHTFELDER: tuple[str, ...] = ("strategie", "zeithorizont", "exit_regeln", "these")


class ExitRegeln(BaseModel):
    """Beim Kauf fixiertes Exit-Regel-Bündel (Vertrag `strategie-exit-regeln`
    §Verträge: `stop_typ, stop_parameter, take_profit, thesis_invalidierung,
    time_box`) — hier nur als durchgereichter Wert; Depot prüft lediglich,
    ob das Bündel bei einem Kauf überhaupt vorhanden ist (AC1)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    stop_typ: str | None = None
    stop_parameter: float | None = None
    take_profit: float | None = None
    thesis_invalidierung: str | None = None
    time_box: str | None = None


class FillInput(BaseModel):
    """Ausführungsergebnis vom Kauf-/Verkaufsmodul (Verträge, Spec `depot`).

    Alle universellen Felder sind Pflicht (AC10); bei `richtung == "kauf"`
    müssen zusätzlich `strategie`, `zeithorizont`, `exit_regeln` und
    `these` gesetzt sein (AC1) — geprüft im `model_validator` unten, nicht
    über bedingungslose Required-Felder (bei Verkauf bleiben sie `None`).
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    # Universeller Dedup-Schlüssel je Fill (ADR-011, P8, `docs/architecture.md`
    # §2/§8) — nachgezogen im DBA-Zweit-Review von S-016 (Critical-Befund):
    # die Redis-Queue liefert Fills at-least-once; `verbuche_fill()`
    # (`app.domain.portfolio.position_booking`) verbucht denselben Wert nie
    # zweimal gegen den Bestand. Stammt aus der Order-Ausführung selbst, wie
    # `mode`/`arrival_price` — kein Depot-intern generierter Wert.
    client_order_id: str = Field(min_length=1)
    titel_id: str = Field(min_length=1)
    anlageklasse: int = Field(ge=1, le=11)
    gics_branche: str = Field(min_length=1)
    richtung: Richtung
    # `gt=0` (Erst-Review-Suggestion, im DBA-Zweit-Review mitgenommen):
    # eine Menge <= 0 ist strukturell kein gültiger Fill (ZeroDivisionError-
    # Schutz für die Kosten-Verteilung in `position_booking`) und zählt wie
    # ein fehlendes Pflichtfeld als AC10/E1-Ablehnungsgrund.
    menge: Decimal = Field(gt=0)
    fill_preis: Decimal
    kosten: Decimal
    arrival_price: Decimal
    waehrung: str = Field(min_length=3, max_length=3)
    zeitstempel: datetime
    mode: Modus

    # Nur bei Kauf Pflicht (AC1) — bei Verkauf `None` zulässig (BR-010: beim
    # ursprünglichen Kauf bereits fixiert, hier nicht erneut nötig).
    strategie: str | None = None
    zeithorizont: int | None = Field(default=None, ge=1, le=9)
    exit_regeln: ExitRegeln | None = None
    these: str | None = None

    @model_validator(mode="after")
    def _pruefe_kauf_pflichtfelder(self) -> "FillInput":
        """AC1: fehlt bei einem Kauf eines der Positions-Attribute
        (Strategie, Zeithorizont, Exit-Regeln, These), verweigert pydantic
        die Instanziierung — die Position wird dadurch nie mit einer
        stillschweigenden Lücke angelegt."""
        if self.richtung == "kauf":
            fehlend = [
                feldname for feldname in _KAUF_PFLICHTFELDER if _ist_leer(getattr(self, feldname))
            ]
            if fehlend:
                raise ValueError("Bei Kauf fehlende Pflichtfelder (AC1): " + ", ".join(fehlend))
        return self


def _ist_leer(wert: object) -> bool:
    """Fehlend heißt hier `None` ODER (bei Strings) ein Leer-/Whitespace-
    String — analog zur bestehenden Konvention in
    `app.contracts.dateneingang.Datenpunkt` (leere Strings zählen als
    fehlendes Pflichtfeld, nicht nur Schlüssel-Abwesenheit)."""
    if wert is None:
        return True
    if isinstance(wert, str):
        return wert.strip() == ""
    return False


class FillProtokollEintrag(BaseModel):
    """Auditierbarer Protokolleintrag für eine abgelehnte Fill-Buchung (AC1
    "protokolliert" / AC10 "protokolliert"). Enthält bewusst keine vollen
    Rohdaten/Secrets — nur die für die Auditierung nötigen strukturierten
    Felder."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    zeitpunkt: datetime
    grund: FillAblehnungsgrund
    titel_id: str | None = None
    richtung: Richtung | None = None
    detail: str


class FillErgebnis(BaseModel):
    """Strukturiertes Ergebnis des Buchungs-Gates
    (`app.domain.portfolio.fill_booking.pruefe_fill`, AC1, AC10). Nur bei
    `status == "abgelehnt"` ist `protokoll_eintrag` gesetzt; nur bei
    `status == "gebucht"` sind `fill`/`resultierende_menge` gesetzt."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    status: Literal["gebucht", "abgelehnt"]
    fill: FillInput | None = None
    resultierende_menge: Decimal | None = None
    grund: FillAblehnungsgrund | None = None
    protokoll_eintrag: FillProtokollEintrag | None = None
