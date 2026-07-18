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

Story S-035 (AC4/AC7) ergänzt den Port um die append-only
Transaktionshistorie: `schreibe_transaktion` (Insert je Fill) und
`historie_je_titel` (Lesen, Grundlage für die TCA je Trade + aggregiert,
AC7). Bewusst KEINE Update-/Delete-Methode im Port — das ist die
App-seitige Hälfte der BR-115-Durchsetzung (siehe
`app.db.models.Transaction`-Docstring): es existiert schlicht kein
Aufrufer-Pfad, über den ein Eintrag nachträglich verändert werden könnte.

Story S-036 (AC8/AC9) ergänzt `alle_offenen_positionen`: eine depotweite
(nicht titel-spezifische) Sicht auf ALLE offenen Lots eines `mode` —
Grundlage für die Portfolio-Aggregate (`app.domain.portfolio
.portfolio_aggregate.berechne_portfolio_aggregat`, AC8) sowie für den
Depot-Stand/Titel+Strategie+Exit-Regeln-Output an Risikomanagement und
Depot-Überwachung (AC9). Anders als `offene_positionen` (ein Titel) liest
diese Methode über ALLE Titel des angegebenen Modus hinweg, inklusive der
(je Lot beim Kauf fixierten) Strategie und Exit-Regeln.

Story S-053 (AC6, FX-Attribution) ergänzt `OffenePosition.einstand_fx_rate`
(Ø-Einstands-FX-Kurs des Lots, `None` bei CHF-Positionen) sowie den
`einstand_fx_rate`-Parameter von `lege_position_an`/`aktualisiere_kauf` und
den `fx_split`-Parameter von `schreibe_transaktion` — Grundlage für die
realisierte FX-Attribution (`app.domain.portfolio.fx_attribution
.berechne_fx_split_realisiert`), persistiert als `Transaction.fx_rate`/
`kapital_gv_chf`/`waehrungs_gv_chf` (data-model.md §4 `transaction`,
→ BR-129).

Story S-054 (AC11, Depot-Dashboard) ergänzt `LivePriceProvider`: den Port
für den Cross-Cutting Socket-Live-Kurs-Zugriff (architecture.md P5,
"die Anzeige-Schicht baut keine eigene Preisanbindung"). Der eigentliche
Live-Kurs-Socket-Adapter (Broker-Feed) ist NICHT Teil dieser Story — analog
zu `ExitRegelnBestand` (S-036, oben: liefert `None`-Felder, solange keine
`exit_rule`-Zeile existiert) liefert die aktuelle Implementierung
(`app.adapters.marketdata.live_price.NoOpLivePriceProvider`) für jeden
Titel `None`; das Dashboard behandelt das gemäss `depot.md` Edge-Cases als
"nicht bewertbar" statt eines veralteten Werts.

Story S-067 (`docs/specs/frontend-cockpit.md` AC6/AC7) ergänzt
`historie_depotweit`: das depotweite (nicht titel-spezifische) Gegenstück
zu `historie_je_titel` (S-035) — schliesst das in AC7 benannte Read-Modell-
Gap (die Trade-Historie lag bislang nur je Titel abfragbar vor), optional
gefiltert nach Titel und Zeitraum. Rein lesend über dieselbe
`transaction`-Tabelle, kein neues Order-Pfad-Verhalten (AC7, Nicht-Ziele).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Protocol

from app.contracts.depot import FillInput, Modus
from app.domain.portfolio.fx_attribution import FxSplit


@dataclass(frozen=True)
class TransaktionsEintrag:
    """Schreibgeschützte Sicht auf einen Eintrag der append-only
    Transaktionshistorie (S-035, AC4/AC7) — bildet das Verträge-Tupel aus
    `docs/specs/depot.md` §Verträge "Transaktionshistorie" ab: `{ trade_id,
    titel_id, richtung, menge, fill_preis, arrival_price, slippage,
    kosten, waehrung, zeitstempel }`, ergänzt in S-053 (AC6) um `fx_rate,
    kapital_gv_chf, waehrungs_gv_chf` (FX-Attribution, → BR-129)."""

    trade_id: str
    titel_id: str
    richtung: str
    menge: Decimal
    fill_preis: Decimal
    arrival_price: Decimal
    slippage: Decimal
    kosten: Decimal
    waehrung: str
    zeitstempel: datetime
    #: AC6 (S-053): FX-Kurs zur CHF-Basiswährung bei diesem Trade, `None`
    #: bei CHF (→ BR-129).
    fx_rate: Decimal | None = None
    #: AC6 (S-053): realisierter Kapitalgewinn-Anteil in CHF — nur bei
    #: einem Fremdwährungs-Verkauf gesetzt, sonst `None`.
    kapital_gv_chf: Decimal | None = None
    #: AC6 (S-053): realisierter Währungsgewinn-Anteil in CHF — nur bei
    #: einem Fremdwährungs-Verkauf gesetzt, sonst `None`.
    waehrungs_gv_chf: Decimal | None = None


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
    #: AC6 (S-053): Ø-Einstands-FX-Kurs des Lots (Kurs zur CHF-Basiswährung
    #: bei Einstand) — `None` bei einer CHF-Position (keine Attribution
    #: nötig, → BR-129).
    einstand_fx_rate: Decimal | None = None


@dataclass(frozen=True)
class ExitRegelnBestand:
    """Schreibgeschützte Sicht auf die beim Kauf fixierten Exit-Regeln
    eines Positions-Lots (S-036, AC9) — bildet `app.db.models.ExitRule`
    ab. Keine Story legt bislang eine `exit_rule`-Zeile an (siehe
    `app.db.models.Position`-Docstring: die inhaltliche Ableitung/
    Persistenz der Exit-Regel-Kategorien ist `strategie-exit-regeln`,
    S-037/S-038) — bis dahin liefert `SqlAlchemyPositionRepository
    .alle_offenen_positionen` hier ein Objekt mit ausschliesslich `None`-
    Feldern (kein Fehler, keine Fiktion eines Werts)."""

    stop_loss_pct: Decimal | None
    take_profit_pct: Decimal | None
    stop_typ: str | None
    atr_multiplikator: Decimal | None
    thesis_invalidation: str | None
    time_box: timedelta | None


@dataclass(frozen=True)
class PositionsBestand:
    """Depotweite, schreibgeschützte Sicht auf einen offenen Positions-Lot
    (S-036, AC8/AC9) — Basis für Portfolio-Aggregate
    (`app.domain.portfolio.portfolio_aggregate.berechne_portfolio_aggregat`)
    sowie für den Depot-Stand-/Titel-Strategie-Exit-Regeln-Output an
    Risikomanagement und Depot-Überwachung. Anders als `OffenePosition`
    (S-016, titel-spezifisch, für die Fill-Buchung) trägt dieses DTO auch
    Anlageklasse, GICS-Branche, Strategie und Exit-Regeln — die für die
    Fill-Buchung selbst irrelevanten, für die Aggregation aber
    erforderlichen Attribute.

    `these`/`zeithorizont_id` (S-040, AC10/AC11): vervollständigen das
    beim Kauf fixierte Attribut-Bündel (Strategie, Zeithorizont,
    Exit-Regeln, These) um die beiden bislang fehlenden Felder — `these`
    macht die Kauf-These maschinell auslesbar (AC10, Grundlage der
    späteren «Analyse bestehende Titel»); `zeithorizont_id` vervollständigt
    das an Risikomanagement/Depot-Überwachung weitergereichte Bündel
    (AC11). Beide sind `None` mit Default, um bestehende Aufrufer/Test-
    Fakes (die diese Felder nicht setzen) nicht zu brechen — bei einer
    real über `SqlAlchemyPositionRepository.alle_offenen_positionen`
    gelesenen Position sind sie stets gesetzt (`Position.these`/
    `Position.time_horizon_id` sind NOT NULL).

    `korrelations_cluster` (S-045, `docs/specs/risikomanagement.md` AC9):
    Korrelations-Cluster-Zuordnung (`Instrument.korrelations_cluster`,
    → BR-138) — unabhängig von `gics_branche`, Grundlage der
    Cluster-Konzentrationsprüfung im Risikomanagement-Gate. `None` mit
    Default (analog `gics_branche` NULLable), da keine Story die
    Erst-Anlage der Korrelations-Cluster-Zuordnung besitzt (siehe
    `app.db.models.Instrument`-Docstring)."""

    position_id: str
    titel_id: str
    asset_class_id: int
    gics_branche: str | None
    menge: Decimal
    einstand_preis: Decimal
    strategie: str | None
    exit_regeln: ExitRegelnBestand
    these: str | None = None
    zeithorizont_id: int | None = None
    korrelations_cluster: str | None = None


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
        self,
        fill: FillInput,
        *,
        einstand_preis: Decimal,
        einstand_methode: str,
        einstand_fx_rate: Decimal | None = None,
    ) -> str:
        """Legt einen neuen offenen Positions-Lot für einen Kauf-Fill an
        (erster Kauf eines Titels, oder — bei FIFO — jeder weitere Kauf)
        und liefert die neue `position_id`. `einstand_preis` ist bereits
        gebühren-genettet (AC3) berechnet worden — dieser Port persistiert
        ihn nur. `einstand_fx_rate` (AC6, S-053): der FX-Kurs des Fills bei
        einer Fremdwährungsposition, `None` bei CHF."""
        ...

    def aktualisiere_kauf(
        self,
        position_id: str,
        *,
        neue_menge: Decimal,
        neuer_einstand_preis: Decimal,
        einstand_fx_rate: Decimal | None = None,
    ) -> None:
        """Schreibt einen Nachkauf in einen bestehenden offenen Lot fort
        (gleitender Durchschnitt, AC5/A1): neue Menge + neuer (bereits
        gebühren-genetteter, AC3) Ø-Einstandspreis. `einstand_fx_rate`
        (AC6, S-053): der neue, mengen-gewichtet gemittelte Ø-Einstands-
        FX-Kurs (`app.domain.portfolio.fx_attribution
        .berechne_neuen_einstand_fx_rate_bei_kauf`), `None` bei CHF."""
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

    def schreibe_transaktion(
        self, fill: FillInput, *, position_id: str | None, fx_split: FxSplit | None = None
    ) -> None:
        """AC4/AC7 (S-035): schreibt den Fill unveränderlich in die
        append-only Transaktionshistorie (Titel, Richtung, Menge,
        Fill-Preis, Kosten, Zeitstempel, Währung) — inklusive Arrival-Price
        und der daraus berechneten realisierten Slippage (AC7,
        `app.domain.portfolio.transaction_historie.berechne_slippage`).
        Wird von `verbuche_fill` NACH einer erfolgreichen Positions-Buchung
        aufgerufen (derselbe Commit wie Dedup-Marker + Positions-Mutation).
        `position_id` ist optional — bei einem Verkauf, der bei FIFO
        mehrere Lots verbraucht (A2), ist der Fill keinem einzelnen Lot
        eindeutig zuordenbar (der Verträge-Vertrag der Historie selbst
        referenziert ohnehin nur `titel_id`, keine `position_id`).

        `fx_split` (AC6, S-053): der bereits aggregierte realisierte
        Kapital-/Währungsgewinn-Split (`app.domain.portfolio
        .fx_attribution.berechne_fx_split_realisiert`/`aggregiere_fx_split`)
        — nur bei einem Verkauf-Fill in Fremdwährung gesetzt, sonst `None`
        (kein G/V auf einen Kauf, keine Attribution bei CHF, → BR-129).
        `fill.fx_rate` selbst wird unabhängig von `fx_split` immer
        gespeichert (Referenzwert für spätere Auswertung/Ø-Bildung), sofern
        gesetzt."""
        ...

    def historie_je_titel(self, titel_id: str, *, mode: Modus) -> list[TransaktionsEintrag]:
        """AC4/AC7 (S-035): liefert die vollständige, unveränderte
        Transaktionshistorie eines Titels **im angegebenen `mode`**
        (Mode-Isolation, BR-130), aufsteigend nach Zeitstempel sortiert —
        Grundlage der TCA je Trade (AC7, jeder Eintrag trägt bereits
        Arrival-Price + Slippage) sowie für Steuerauszug/Dashboard (AC4).
        Leere Liste, falls für `titel_id`/`mode` noch kein Fill gebucht
        wurde."""
        ...

    def alle_offenen_positionen(self, *, mode: Modus) -> list[PositionsBestand]:
        """AC8/AC9 (S-036): liefert ALLE offenen Positions-Lots **im
        angegebenen `mode`** (Mode-Isolation, BR-113/BR-130) über sämtliche
        Titel hinweg, inklusive Anlageklasse, GICS-Branche (`Instrument
        .gics_sector`, `None` falls noch nicht gepflegt), Strategie-Name
        und Exit-Regeln (`None`-Felder, solange keine `exit_rule`-Zeile
        existiert, siehe `ExitRegelnBestand`-Docstring). Aufsteigend nach
        `instrument_id`, `opened_at` sortiert (älteste Lot-Zeile je Titel
        zuerst — Voraussetzung für die Dedup-Logik in
        `app.domain.portfolio.portfolio_aggregate
        .ermittle_titel_strategie_exit_regeln`, die bei mehreren Lots
        desselben Titels (FIFO) den ältesten Lot als Titel-Repräsentant
        verwendet). Leere Liste, falls kein offener Lot in diesem Modus
        existiert.

        **S-040 (AC10/AC11):** liefert zusätzlich `these`/`zeithorizont_id`
        je Lot — vervollständigt das beim Kauf fixierte Attribut-Bündel."""
        ...

    def historie_depotweit(
        self,
        *,
        mode: Modus,
        titel_id: str | None = None,
        von: datetime | None = None,
        bis: datetime | None = None,
    ) -> list[TransaktionsEintrag]:
        """AC6/AC7 (S-067, `docs/specs/frontend-cockpit.md`): liefert die
        depotweite (nicht titel-spezifische) Fill-/Transaktionshistorie
        **im angegebenen `mode`** (Mode-Isolation, BR-130) — schliesst das
        in AC7 benannte Read-Modell-Gap (die Trade-Historie lag bislang nur
        als `historie_je_titel`, S-035, je Titel abfragbar vor). Optional
        zusätzlich gefiltert auf `titel_id` (exakte Titel-UUID; ist sie
        keine gültige UUID, liefert dies eine leere Liste statt eines
        Fehlers, analog `historie_je_titel`) und/oder den beidseitig
        inklusiven Zeitraum `[von, bis]` (Vergleich gegen `booked_at`) —
        `None` heisst je "kein Filter". Aufsteigend nach `booked_at`
        sortiert (wie `historie_je_titel`). Leere Liste, falls im Modus
        (bzw. im gefilterten Ausschnitt) kein Fill gebucht wurde."""
        ...


class LivePriceProvider(Protocol):
    """Cross-Cutting Socket-Live-Kurs-Zugriff (AC11, architecture.md P5) —
    die einzige erlaubte Quelle für aktuelle Kurse im Depot-Dashboard
    (`app.api.dashboard`); das Dashboard implementiert selbst keine eigene
    Preisanbindung, sondern liest ausschliesslich über diesen Port."""

    def aktueller_preis(self, titel_id: str) -> Decimal | None:
        """Liefert den aktuellen Live-Kurs für `titel_id`, oder `None`,
        falls kein aktueller Kurs vorliegt (`depot.md` Edge-Cases: dann gilt
        die Position als "nicht bewertbar" statt mit einem veralteten Wert
        ausgewiesen zu werden)."""
        ...
