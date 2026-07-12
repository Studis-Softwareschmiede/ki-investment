"""Repository-Port für das Depotmodul (Modul 16, architecture.md §4:
"abstrakte Protokolle in `app/domain/**/ports.py`", P1).

Der reine Domain-Kern (`app.domain.portfolio.fill_booking`,
`app.domain.portfolio.position_booking`) darf laut P1 kein SQLAlchemy/DB
importieren — er greift auf den Bestand ausschliesslich über dieses
`Protocol` zu; die konkrete Implementierung liegt im Adapter
`app.adapters.repositories.position_repository.SqlAlchemyPositionRepository`.

Story S-016 (AC2/AC3/AC5) erweitert den Port um die Schreib-/Fortschreibungs-
Methoden für die eigentliche Positions-Buchung (Ø-Einstand/Gebühren-Netting,
Einstand-Methode gleitender Ø/FIFO). Modellannahme (deckt sich mit der
bereits in S-015 vorgesehenen "mehrere offene Positionen desselben Titels"-
Möglichkeit, siehe `SqlAlchemyPositionRepository.aktuelle_menge`): **jede**
`position`-Zeile ist ein einzelner Einstands-„Lot" — bei gleitendem
Durchschnitt bleibt je Titel genau ein offener Lot bestehen (Nachkäufe
mitteln in ihn hinein), bei FIFO legt jeder Kauf einen neuen Lot an und ein
Verkauf verbraucht die offenen Lots in `opened_at`-Reihenfolge (älteste
zuerst).

DBA-Zweit-Review von S-016 (Critical + Important) ergänzt zwei weitere
Verhaltensanforderungen an den Port:
- **Idempotenz (ADR-011, P8):** `markiere_fill_verbucht` ist der
  Dedup-Check/-Marker, den `app.domain.portfolio.position_booking
  .verbuche_fill` vor jeder Mutation aufruft — ein bereits verbuchter
  `client_order_id`-Wert darf die Position nie ein zweites Mal fortschreiben
  (At-least-once-Zustellung, Redis-Queue).
- **Gesperrte Lots (Lost-Update/TOCTOU):** `offene_positionen` liefert die
  für eine Mutation vorgesehenen Lots **gesperrt** (`SELECT … FOR UPDATE`
  unter Postgres — unter SQLite, das dies nicht unterstützt, wirkungslos-
  aber-fehlerfrei), damit zwei parallele Buchungen desselben Titels nicht
  denselben veralteten Lot-Stand lesen und einander überschreiben.

DBA-Re-Review (Iteration 3, Important) ergänzt **Mode-Isolation
(BR-113/BR-130):** `offene_positionen`/`aktuelle_menge` nehmen jetzt ein
verpflichtendes `mode`-Argument und filtern die zurückgelieferten/summierten
Lots zusätzlich auf `position.mode == mode` — ein "echt"-Fill darf niemals
gegen einen "simuliert"-Lot desselben Titels gemittelt, verbraucht oder
gedeckt werden (und umgekehrt). `mode` stammt in beiden Aufrufern
(`position_booking._verbuche_kauf`/`_verbuche_verkauf`,
`fill_booking.pruefe_fill`) aus `fill.mode` — nie aus einer globalen
Konfiguration.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Protocol

from app.contracts.depot import FillInput, Modus


@dataclass(frozen=True)
class OffenePosition:
    """Schreibgeschützte Sicht auf einen offenen Positions-Lot (S-016) —
    die für Ø-Einstand-/G-V-Berechnung + FIFO-Verbrauchsreihenfolge
    benötigten Felder, ohne den Domain-Kern an das ORM zu binden (P1)."""

    position_id: str
    menge: Decimal
    einstand_preis: Decimal
    einstand_methode: str
    opened_at: datetime


class PositionRepository(Protocol):
    """Lese-/Schreib-Zugriff auf den Positions-Bestand."""

    def aktuelle_menge(self, titel_id: str, *, mode: Modus) -> Decimal:
        """Liefert die Summe der `menge` aller offenen Positionen für
        `titel_id` **im angegebenen `mode`** (`Decimal("0")`, falls keine
        offene Position existiert). Mode-Isolation (BR-113/BR-130, DBA-
        Re-Review S-016, Iteration 3): ein "echt"-Bestand darf nie
        "simuliert"-Lots desselben Titels mitzählen (und umgekehrt)."""
        ...

    def offene_positionen(self, titel_id: str, *, mode: Modus) -> list[OffenePosition]:
        """Liefert alle offenen Positions-Lots für `titel_id` **im
        angegebenen `mode`**, aufsteigend nach `opened_at` sortiert
        (älteste zuerst — Voraussetzung für die FIFO-Verbrauchsreihenfolge,
        AC5/A2). Leere Liste, falls keine offene Position in diesem Modus
        existiert (erster Kauf eines Titels in diesem Modus). Die
        zurückgelieferten Zeilen sind für eine nachfolgende Mutation
        **gesperrt** gelesen (`SELECT … FOR UPDATE` unter Postgres, DBA-
        Zweit-Review S-016: verhindert Lost-Update bei parallelen
        Buchungen desselben Titels). Mode-Isolation (BR-113/BR-130, DBA-
        Re-Review S-016, Iteration 3): filtert zusätzlich auf
        `position.mode == mode` — ein "echt"-Fill darf niemals gegen einen
        "simuliert"-Lot desselben Titels gemittelt oder verbraucht werden
        (und umgekehrt)."""
        ...

    def lege_position_an(
        self, fill: FillInput, *, einstand_preis: Decimal, einstand_methode: str
    ) -> str:
        """Legt einen neuen offenen Positions-Lot für einen Kauf-Fill an
        (erster Kauf eines Titels, oder — bei FIFO — jeder weitere Kauf)
        und liefert die neue `position_id`. `einstand_preis` ist bereits
        gebühren-genettet (AC3) berechnet worden — dieser Port persistiert
        ihn nur."""
        ...

    def aktualisiere_kauf(
        self, position_id: str, *, neue_menge: Decimal, neuer_einstand_preis: Decimal
    ) -> None:
        """Schreibt einen Nachkauf in einen bestehenden offenen Lot fort
        (gleitender Durchschnitt, AC5/A1): neue Menge + neuer (bereits
        gebühren-genetteter, AC3) Ø-Einstandspreis."""
        ...

    def verbuche_verkauf_lot(
        self, position_id: str, *, neue_menge: Decimal, realisierter_gv_delta: Decimal
    ) -> None:
        """Verbucht den Verkaufs-Anteil eines einzelnen Lots: setzt die
        neue Restmenge, addiert `realisierter_gv_delta` auf
        `realisierter_gv` (AC2/AC3) und schliesst den Lot (Status
        `geschlossen`, `closed_at` gesetzt), sobald `neue_menge == 0`
        (Vollverkauf des Lots) — der Ø-Einstandspreis des Lots selbst
        bleibt dabei unverändert (AC5/A1: nur bei gleitendem Durchschnitt
        fachlich relevant, bei FIFO ohnehin je Lot fix)."""
        ...

    def markiere_fill_verbucht(self, client_order_id: str, *, titel_id: str, richtung: str) -> bool:
        """Idempotenz-Check + -Marker (ADR-011, P8; DBA-Zweit-Review
        S-016, Critical-Befund): versucht `client_order_id` atomar als
        verbucht zu markieren. Liefert `True`, wenn dies das erste Mal ist
        (der Fill darf fortgeschrieben werden); `False`, wenn
        `client_order_id` bereits existiert — At-least-once-Zustellung
        (Redis-Queue) hat denselben Fill doppelt zugestellt,
        `verbuche_fill` bricht in diesem Fall ohne weitere Mutation ab
        (Bestand unverändert)."""
        ...
