"""SQLAlchemy-Implementierung des `PositionRepository`-Ports (architecture.md
§4 `app/adapters/repositories/`, Modul 16 Depotmodul, S-015 + S-016).

Implementiert `app.domain.portfolio.ports.PositionRepository` strukturell
(Protocol, keine explizite Vererbung nötig) gegen die `position`-Tabelle
(`app.db.models.Position`, `docs/data-model.md` §4).

S-016 (AC2/AC3/AC5) ergänzt die Schreib-/Fortschreibungs-Methoden
(`offene_positionen`, `lege_position_an`, `aktualisiere_kauf`,
`verbuche_verkauf_lot`) — siehe `app.domain.portfolio.ports` für die
Modellannahme ("jede `position`-Zeile ist ein Lot"). `lege_position_an`
legt bewusst **keine** `exit_rule`-Zeile an: die inhaltliche Interpretation
der Exit-Regel-Kategorien ist `strategie-exit-regeln` (S-037/S-038), nicht
Teil dieser Story (siehe `app.contracts.depot`-Moduldocstring).

DBA-Zweit-Review von S-016 (Critical + Important) ergänzt:
- `offene_positionen` liest die Lots jetzt gesperrt (`with_for_update()`) —
  verhindert, dass zwei parallele Buchungen desselben Titels denselben
  veralteten Lot-Stand lesen (Lost-Update/TOCTOU).
- `markiere_fill_verbucht` implementiert den ADR-011-Dedup-Check gegen die
  neue `depot_fill_dedup`-Tabelle (data-model.md §4): ein `IntegrityError`
  beim Insert (PK-Verletzung auf `client_order_id`) heisst „bereits
  verbucht" — kein Crash, sondern ein struktureller `False`-Rückgabewert.

DBA-Re-Review (Iteration 3, Important) ergänzt **Mode-Isolation
(BR-113/BR-130):** `offene_positionen` und `aktuelle_menge` filtern jetzt
zusätzlich auf `Position.mode == mode` — ein „echt"-Fill darf nie gegen
einen „simuliert"-Lot desselben Titels gemittelt, verbraucht oder gedeckt
werden (und umgekehrt). Beide Aufrufer (`position_booking`, `fill_booking`)
übergeben durchgängig `fill.mode`.

Story S-035 (AC4/AC7) ergänzt `schreibe_transaktion` (Insert je Fill in
die append-only `transaction`-Historie, inkl. Arrival-Price/Slippage) und
`historie_je_titel` (Lesen, chronologisch sortiert, Mode-isoliert) —
siehe `app.db.models.Transaction`-Docstring für die App-seitige
BR-115-Durchsetzung (keine Update-/Delete-Methode existiert in diesem
Adapter für diese Tabelle).

Story S-036 (AC8/AC9) ergänzt `alle_offenen_positionen`: liest ALLE
offenen Lots eines `mode` über sämtliche Titel hinweg (nicht nur einen,
wie `offene_positionen`), inklusive Anlageklasse, GICS-Branche
(`Instrument.gics_sector`, Outer-Join-Attribut, da nicht auf `Position`
selbst gepflegt), Strategie-Name (`Strategy.name`) und Exit-Regeln
(`ExitRule`, Outer-Join — noch keine Story legt `exit_rule`-Zeilen an,
siehe `app.domain.portfolio.ports.ExitRegelnBestand`-Docstring). Basis für
`app.domain.portfolio.portfolio_aggregate` (Portfolio-Aggregate,
Depot-Stand, Titel-Strategie-Exit-Regeln-Output).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.contracts.depot import FillInput, Modus
from app.db.models import DepotFillDedup, ExitRule, Instrument, Position, Strategy, Transaction
from app.domain.portfolio.ports import (
    ExitRegelnBestand,
    OffenePosition,
    PositionsBestand,
    TransaktionsEintrag,
)
from app.domain.portfolio.transaction_historie import berechne_slippage


class SqlAlchemyPositionRepository:
    """Liest/schreibt den Positions-Bestand über eine injizierte
    SQLAlchemy-`Session` (Ports & Adapters, P1 — kein eigenes
    Connection-/Engine-Management hier)."""

    def __init__(self, session: Session) -> None:
        self._session = session

    def aktuelle_menge(self, titel_id: str, *, mode: Modus) -> Decimal:
        """Summe der `menge` aller offenen (`status == "offen"`) Positionen
        für `titel_id` **im angegebenen `mode`** (Mode-Isolation, BR-113/
        BR-130, DBA-Re-Review S-016 Iteration 3) — `Decimal("0")`, falls
        keine offene Position in diesem Modus existiert (oder `titel_id`
        keine gültige UUID ist — dann kann strukturell keine Position dazu
        existieren). Eine Summe statt einer Einzelwert-Abfrage deckt auch
        den (vom Modell nicht ausgeschlossenen) Fall mehrerer offener
        Positionen desselben Titels konsistent ab."""
        instrument_id = _als_uuid(titel_id)
        if instrument_id is None:
            return Decimal("0")

        stmt = select(Position.menge).where(
            Position.instrument_id == instrument_id,
            Position.status == "offen",
            Position.mode == mode,
        )
        mengen = self._session.scalars(stmt).all()
        return sum(mengen, Decimal("0"))

    def offene_positionen(self, titel_id: str, *, mode: Modus) -> list[OffenePosition]:
        """Alle offenen Lots für `titel_id` **im angegebenen `mode`**
        (Mode-Isolation, BR-113/BR-130, DBA-Re-Review S-016 Iteration 3:
        ein „echt"-Fill darf nie gegen einen „simuliert"-Lot desselben
        Titels gemittelt oder verbraucht werden, und umgekehrt), aufsteigend
        nach `opened_at` sortiert (älteste zuerst — FIFO-Verbrauchs-
        reihenfolge, AC5/A2). Gesperrt gelesen (`with_for_update()`, DBA-
        Zweit-Review S-016): diese Methode wird ausschliesslich vor einer
        Mutation der gelesenen Lots aufgerufen (`position_booking
        ._verbuche_kauf`/`_verbuche_verkauf`) — die Sperre verhindert, dass
        eine zweite, parallele Buchung desselben Titels denselben
        veralteten Stand liest, bevor die erste ihre Änderung committet hat
        (Lost-Update). Unter SQLite (Tests) ist `FOR UPDATE` wirkungslos,
        aber fehlerfrei (kein Zeilensperren-Support, kein Fehler)."""
        instrument_id = _als_uuid(titel_id)
        if instrument_id is None:
            return []

        stmt = (
            select(Position)
            .where(
                Position.instrument_id == instrument_id,
                Position.status == "offen",
                Position.mode == mode,
            )
            .order_by(Position.opened_at.asc())
            .with_for_update()
        )
        positionen = self._session.scalars(stmt).all()
        return [
            OffenePosition(
                position_id=str(p.id),
                menge=p.menge,
                einstand_preis=p.einstand_preis,
                einstand_methode=p.einstand_methode,
                opened_at=p.opened_at,
            )
            for p in positionen
        ]

    def lege_position_an(
        self, fill: FillInput, *, einstand_preis: Decimal, einstand_methode: str
    ) -> str:
        """Legt einen neuen offenen Lot für einen Kauf-Fill an (AC2/AC3/
        AC5) — löst `fill.strategie` (Name) gegen `strategy.id` auf;
        `fill.anlageklasse`/`fill.zeithorizont` sind bereits identische
        Fremdschlüsselwerte (`asset_class_id`/`time_horizon_id`)."""
        strategy_id = self._session.scalars(
            select(Strategy.id).where(Strategy.name == fill.strategie)
        ).first()
        if strategy_id is None:
            raise ValueError(
                f"Unbekannte Strategie {fill.strategie!r} — Position kann nicht angelegt werden."
            )

        position = Position(
            id=uuid.uuid4(),
            instrument_id=uuid.UUID(fill.titel_id),
            asset_class_id=fill.anlageklasse,
            strategy_id=strategy_id,
            time_horizon_id=fill.zeithorizont,
            these=fill.these,
            menge=fill.menge,
            einstand_preis=einstand_preis,
            einstand_methode=einstand_methode,
            status="offen",
            mode=fill.mode,
        )
        self._session.add(position)
        self._session.flush()
        return str(position.id)

    def aktualisiere_kauf(
        self, position_id: str, *, neue_menge: Decimal, neuer_einstand_preis: Decimal
    ) -> None:
        """Schreibt einen Nachkauf in einen bestehenden Lot fort
        (gleitender Durchschnitt, AC5/A1)."""
        position = self._session.get(Position, uuid.UUID(position_id))
        if position is None:
            raise ValueError(f"Position {position_id!r} nicht gefunden.")
        position.menge = neue_menge
        position.einstand_preis = neuer_einstand_preis

    def verbuche_verkauf_lot(
        self, position_id: str, *, neue_menge: Decimal, realisierter_gv_delta: Decimal
    ) -> None:
        """Verbucht den Verkaufs-Anteil eines Lots (AC2/AC3): neue
        Restmenge, `realisierter_gv` fortgeschrieben; bei Vollverkauf des
        Lots (`neue_menge == 0`) wird der Lot geschlossen — die
        append-only Transaktionshistorie selbst wird NICHT hier, sondern
        separat über `schreibe_transaktion` (S-035, AC4) fortgeschrieben
        und bleibt von einer Lot-Schliessung unberührt bestehen."""
        position = self._session.get(Position, uuid.UUID(position_id))
        if position is None:
            raise ValueError(f"Position {position_id!r} nicht gefunden.")
        position.menge = neue_menge
        position.realisierter_gv = position.realisierter_gv + realisierter_gv_delta
        if neue_menge == 0:
            position.status = "geschlossen"
            position.closed_at = datetime.now(UTC)

    def markiere_fill_verbucht(self, client_order_id: str, *, titel_id: str, richtung: str) -> bool:
        """ADR-011-Dedup-Check + -Marker (DBA-Zweit-Review S-016, Critical-
        Befund): fügt eine `depot_fill_dedup`-Zeile ein — der PK
        (`client_order_id`) erzwingt Einzigartigkeit auf DB-Ebene. Liefert
        `True` bei erfolgreichem (erstem) Insert, `False` bei
        `IntegrityError` (Fill wurde bereits verbucht — At-least-once-
        Zustellung). Muss als erste Repository-Operation von
        `verbuche_fill` aufgerufen werden (vor jeder Positions-Mutation),
        damit ein `False`-Ergebnis den Bestand garantiert unverändert
        lässt."""
        eintrag = DepotFillDedup(
            client_order_id=client_order_id,
            instrument_id=uuid.UUID(titel_id),
            richtung=richtung,
        )
        self._session.add(eintrag)
        try:
            self._session.flush()
        except IntegrityError:
            self._session.rollback()
            return False
        return True

    def schreibe_transaktion(self, fill: FillInput, *, position_id: str | None) -> None:
        """AC4/AC7 (S-035): fügt der append-only `transaction`-Historie
        einen unveränderlichen Eintrag für `fill` hinzu — `typ` bildet
        `fill.richtung` ab (`kauf`→`buy`, `verkauf`→`sell`),
        `slippage_abs` wird über die reine Domain-Formel
        (`app.domain.portfolio.transaction_historie.berechne_slippage`)
        berechnet, nicht hier neu erfunden. `kosten_chf`/`preis` speichern
        `fill.kosten`/`fill.fill_preis` unverändert (keine FX-Umrechnung —
        das ist AC6/S-053, ausserhalb dieser Story, analog zur bestehenden
        Behandlung von `Position.einstand_preis`/`realisierter_gv`)."""
        typ = "buy" if fill.richtung == "kauf" else "sell"
        zeile = Transaction(
            id=uuid.uuid4(),
            position_id=uuid.UUID(position_id) if position_id is not None else None,
            instrument_id=uuid.UUID(fill.titel_id),
            typ=typ,
            menge=fill.menge,
            preis=fill.fill_preis,
            kosten_chf=fill.kosten,
            waehrung=fill.waehrung,
            arrival_price=fill.arrival_price,
            slippage_abs=berechne_slippage(fill.fill_preis, fill.arrival_price),
            mode=fill.mode,
            booked_at=fill.zeitstempel,
        )
        self._session.add(zeile)
        self._session.flush()

    def historie_je_titel(self, titel_id: str, *, mode: Modus) -> list[TransaktionsEintrag]:
        """AC4/AC7 (S-035): vollständige, unveränderte Transaktionshistorie
        für `titel_id` **im angegebenen `mode`** (Mode-Isolation, BR-130),
        aufsteigend nach `booked_at` sortiert. Leere Liste, falls
        `titel_id` keine gültige UUID ist oder noch kein Fill gebucht
        wurde."""
        instrument_id = _als_uuid(titel_id)
        if instrument_id is None:
            return []

        stmt = (
            select(Transaction)
            .where(Transaction.instrument_id == instrument_id, Transaction.mode == mode)
            .order_by(Transaction.booked_at.asc())
        )
        zeilen = self._session.scalars(stmt).all()
        return [
            TransaktionsEintrag(
                trade_id=str(z.id),
                titel_id=str(z.instrument_id),
                richtung="kauf" if z.typ == "buy" else "verkauf",
                menge=z.menge,
                fill_preis=z.preis,
                arrival_price=z.arrival_price,
                slippage=z.slippage_abs,
                kosten=z.kosten_chf,
                waehrung=z.waehrung,
                zeitstempel=z.booked_at,
            )
            for z in zeilen
        ]

    def alle_offenen_positionen(self, *, mode: Modus) -> list[PositionsBestand]:
        """AC8/AC9 (S-036): depotweite Sicht auf ALLE offenen Lots **im
        angegebenen `mode`** (Mode-Isolation, BR-113/BR-130), aufsteigend
        nach `instrument_id`, `opened_at` sortiert (ältester Lot je Titel
        zuerst — Voraussetzung für die Titel-Dedup-Logik in
        `app.domain.portfolio.portfolio_aggregate
        .ermittle_titel_strategie_exit_regeln`). `Instrument`/`ExitRule`
        werden als Outer-Join angebunden: `gics_sector` kann fehlen (siehe
        `app.db.models.Instrument`-Docstring), eine `exit_rule`-Zeile
        existiert bislang für keinen Lot (S-037/S-038)."""
        stmt = (
            select(Position, Instrument.gics_sector, Strategy.name, ExitRule)
            .join(Instrument, Instrument.id == Position.instrument_id)
            .join(Strategy, Strategy.id == Position.strategy_id)
            .outerjoin(ExitRule, ExitRule.position_id == Position.id)
            .where(Position.status == "offen", Position.mode == mode)
            .order_by(Position.instrument_id.asc(), Position.opened_at.asc())
        )
        zeilen = self._session.execute(stmt).all()
        return [
            PositionsBestand(
                position_id=str(position.id),
                titel_id=str(position.instrument_id),
                asset_class_id=position.asset_class_id,
                gics_branche=gics_sector,
                menge=position.menge,
                einstand_preis=position.einstand_preis,
                strategie=strategie_name,
                exit_regeln=_exit_regeln_aus_zeile(exit_rule_zeile),
            )
            for position, gics_sector, strategie_name, exit_rule_zeile in zeilen
        ]


def _exit_regeln_aus_zeile(zeile: ExitRule | None) -> ExitRegelnBestand:
    """AC9 (S-036): bildet eine `exit_rule`-Zeile auf `ExitRegelnBestand`
    ab — existiert (noch) keine Zeile (kein Aufrufer legt bislang eine an,
    S-037/S-038), liefert dies ein Objekt mit ausschliesslich `None`-
    Feldern statt eines Fehlers."""
    if zeile is None:
        return ExitRegelnBestand(
            stop_loss_pct=None,
            take_profit_pct=None,
            stop_typ=None,
            atr_multiplikator=None,
            thesis_invalidation=None,
            time_box=None,
        )
    return ExitRegelnBestand(
        stop_loss_pct=zeile.stop_loss_pct,
        take_profit_pct=zeile.take_profit_pct,
        stop_typ=zeile.stop_typ,
        atr_multiplikator=zeile.atr_multiplikator,
        thesis_invalidation=zeile.thesis_invalidation,
        time_box=zeile.time_box,
    )


def _als_uuid(titel_id: str) -> uuid.UUID | None:
    try:
        return uuid.UUID(titel_id)
    except (ValueError, AttributeError, TypeError):
        return None
