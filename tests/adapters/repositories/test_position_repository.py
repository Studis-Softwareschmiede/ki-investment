"""Tests für `SqlAlchemyPositionRepository` (Story S-015 + S-016 + S-016
DBA-Zweit-Review).

Covers (depot): AC10, AC2, AC3, AC5

Deckt die Bestandsermittlung, auf der `app.domain.portfolio.fill_booking
.pruefe_fill` die AC10-Prüfung "keine resultierende negative Menge"
aufbaut: `aktuelle_menge()` liefert 0 ohne offene Position, die Menge einer
einzelnen offenen Position, die Summe mehrerer offener Positionen und
ignoriert geschlossene Positionen.

S-016 (AC2/AC3/AC5) ergänzt die Schreib-/Fortschreibungs-Methoden, die
`app.domain.portfolio.position_booking.verbuche_fill` nutzt:
`offene_positionen` (sortiert nach `opened_at`), `lege_position_an`
(inkl. Strategie-Namensauflösung), `aktualisiere_kauf` (gleitender
Durchschnitt) und `verbuche_verkauf_lot` (Restmenge + `realisierter_gv`
fortgeschrieben, Lot-Schliessung bei Vollverkauf).

DBA-Zweit-Review von S-016 (Critical, ADR-011/P8) ergänzt
`markiere_fill_verbucht` (Idempotenz-Ledger `depot_fill_dedup`): ein
erster Aufruf mit einer `client_order_id` liefert `True`, ein zweiter
Aufruf mit DERSELBEN `client_order_id` liefert `False` (PK-Verletzung,
sauber als struktureller Rückgabewert abgefangen statt als Crash).

DBA-Re-Review S-016 (Iteration 3, Important — Mode-Isolation, BR-113/
BR-130) ergänzt `test_aktuelle_menge_zaehlt_nur_den_eigenen_modus` und
`test_offene_positionen_filtert_nach_modus`: ein Titel mit gleichzeitig
einer „echt"- und einer „simuliert"-Position darf über `mode=...` nur die
Zeile(n) des angefragten Modus liefern.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.adapters.repositories.position_repository import SqlAlchemyPositionRepository
from app.contracts.depot import ExitRegeln, FillInput
from app.db.base import Base
from app.db.models import AssetClass, DepotFillDedup, Instrument, Position, Strategy, TimeHorizon


def _make_engine():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return engine


def _seed_stammdaten(session: Session) -> tuple[uuid.UUID, uuid.UUID]:
    # `id`-Spalten (UUID) tragen `server_default=gen_random_uuid()` (nur
    # unter Postgres verfügbar) — unter SQLite (In-Memory) daher explizit.
    session.add(AssetClass(id=1, name="Aktien", prio_stufe="MVP", aktiv=True, retail_driven=True))
    session.add(TimeHorizon(id=8, name="Buy-and-Hold"))
    strategy = Strategy(id=uuid.uuid4(), name="Index")
    session.add(strategy)
    instrument = Instrument(
        id=uuid.uuid4(), symbol="ACME", name="Acme Corp", asset_class_id=1, currency="CHF"
    )
    session.add(instrument)
    session.commit()
    return instrument.id, strategy.id


def _make_position(
    instrument_id, strategy_id, *, menge: Decimal, status: str, mode: str = "simuliert"
) -> Position:
    return Position(
        id=uuid.uuid4(),
        instrument_id=instrument_id,
        asset_class_id=1,
        strategy_id=strategy_id,
        time_horizon_id=8,
        these="These.",
        menge=menge,
        einstand_preis=Decimal("100"),
        mode=mode,
        status=status,
    )


def _kauf_fill(instrument_id: uuid.UUID, **overrides: object) -> FillInput:
    kwargs = {
        "client_order_id": "order-1",
        "titel_id": str(instrument_id),
        "anlageklasse": 1,
        "gics_branche": "Technology",
        "richtung": "kauf",
        "menge": Decimal("10"),
        "fill_preis": Decimal("100"),
        "kosten": Decimal("10"),
        "arrival_price": Decimal("100"),
        "waehrung": "CHF",
        "zeitstempel": datetime(2026, 7, 12, 10, 0, tzinfo=UTC),
        "mode": "simuliert",
        "strategie": "Index",
        "zeithorizont": 8,
        "exit_regeln": ExitRegeln(stop_typ="atr_trailing", stop_parameter=2.5),
        "these": "Langfristiger Index-Halter.",
    }
    kwargs.update(overrides)
    return FillInput(**kwargs)


def test_aktuelle_menge_ist_null_ohne_offene_position() -> None:
    """@trace depot#AC10 — kein Bestand für einen Titel ohne (offene)
    Position ergibt 0, nicht einen Fehler."""
    engine = _make_engine()
    with Session(engine) as session:
        instrument_id, _strategy_id = _seed_stammdaten(session)
        repository = SqlAlchemyPositionRepository(session)
        assert repository.aktuelle_menge(str(instrument_id), mode="simuliert") == Decimal("0")


def test_aktuelle_menge_liefert_menge_der_offenen_position() -> None:
    """@trace depot#AC10 — Bestand einer einzelnen offenen Position."""
    engine = _make_engine()
    with Session(engine) as session:
        instrument_id, strategy_id = _seed_stammdaten(session)
        session.add(_make_position(instrument_id, strategy_id, menge=Decimal("42"), status="offen"))
        session.commit()

        repository = SqlAlchemyPositionRepository(session)
        assert repository.aktuelle_menge(str(instrument_id), mode="simuliert") == Decimal("42")


def test_aktuelle_menge_ignoriert_geschlossene_positionen() -> None:
    """@trace depot#AC10 — eine geschlossene Position (Menge 0, aber
    historisch mit einem Wert denkbar) zählt nicht zum aktuellen Bestand."""
    engine = _make_engine()
    with Session(engine) as session:
        instrument_id, strategy_id = _seed_stammdaten(session)
        session.add(
            _make_position(instrument_id, strategy_id, menge=Decimal("0"), status="geschlossen")
        )
        session.commit()

        repository = SqlAlchemyPositionRepository(session)
        assert repository.aktuelle_menge(str(instrument_id), mode="simuliert") == Decimal("0")


def test_aktuelle_menge_summiert_mehrere_offene_positionen() -> None:
    """@trace depot#AC10 — mehrere offene Positionen desselben Titels
    (vom Modell nicht ausgeschlossen) werden summiert statt nur die erste
    zu liefern."""
    engine = _make_engine()
    with Session(engine) as session:
        instrument_id, strategy_id = _seed_stammdaten(session)
        session.add(_make_position(instrument_id, strategy_id, menge=Decimal("10"), status="offen"))
        session.add(_make_position(instrument_id, strategy_id, menge=Decimal("5"), status="offen"))
        session.commit()

        repository = SqlAlchemyPositionRepository(session)
        assert repository.aktuelle_menge(str(instrument_id), mode="simuliert") == Decimal("15")


def test_aktuelle_menge_zaehlt_nur_den_eigenen_modus() -> None:
    """@trace depot#AC10 — DBA-Re-Review S-016 (Iteration 3, Important,
    BR-113/BR-130): ein Titel mit gleichzeitig einer "echt"- und einer
    "simuliert"-Position darf im jeweils angefragten Modus NUR die eigene
    Menge liefern — "echt" zählt nicht "simuliert" mit (und umgekehrt)."""
    engine = _make_engine()
    with Session(engine) as session:
        instrument_id, strategy_id = _seed_stammdaten(session)
        session.add(
            _make_position(
                instrument_id, strategy_id, menge=Decimal("10"), status="offen", mode="echt"
            )
        )
        session.add(
            _make_position(
                instrument_id, strategy_id, menge=Decimal("100"), status="offen", mode="simuliert"
            )
        )
        session.commit()

        repository = SqlAlchemyPositionRepository(session)
        assert repository.aktuelle_menge(str(instrument_id), mode="echt") == Decimal("10")
        assert repository.aktuelle_menge(str(instrument_id), mode="simuliert") == Decimal("100")


def test_offene_positionen_ist_leer_ohne_bestand() -> None:
    """@trace depot#AC5 — kein offener Lot für einen Titel ohne Position
    ergibt eine leere Liste, kein Fehler."""
    engine = _make_engine()
    with Session(engine) as session:
        instrument_id, _strategy_id = _seed_stammdaten(session)
        repository = SqlAlchemyPositionRepository(session)
        assert repository.offene_positionen(str(instrument_id), mode="simuliert") == []


def test_offene_positionen_sortiert_aufsteigend_nach_opened_at() -> None:
    """@trace depot#AC5 — die FIFO-Verbrauchsreihenfolge (A2) setzt
    voraus, dass `offene_positionen` älteste zuerst liefert."""
    engine = _make_engine()
    with Session(engine) as session:
        instrument_id, strategy_id = _seed_stammdaten(session)
        aelterer = _make_position(instrument_id, strategy_id, menge=Decimal("10"), status="offen")
        aelterer.opened_at = datetime(2026, 1, 1, tzinfo=UTC)
        aelterer.einstand_methode = "fifo"
        juengerer = _make_position(instrument_id, strategy_id, menge=Decimal("5"), status="offen")
        juengerer.opened_at = datetime(2026, 6, 1, tzinfo=UTC)
        juengerer.einstand_methode = "fifo"
        # Absichtlich in "falscher" Reihenfolge hinzugefügt, um die
        # `ORDER BY opened_at`-Sortierung zu erzwingen statt Insert-Reihenfolge.
        session.add(juengerer)
        session.add(aelterer)
        session.commit()

        repository = SqlAlchemyPositionRepository(session)
        lots = repository.offene_positionen(str(instrument_id), mode="simuliert")
        assert [lot.position_id for lot in lots] == [str(aelterer.id), str(juengerer.id)]


def test_offene_positionen_filtert_nach_modus() -> None:
    """@trace depot#AC5 — DBA-Re-Review S-016 (Iteration 3, Important,
    BR-113/BR-130): ein Titel mit gleichzeitig einer "echt"- und einer
    "simuliert"-Position darf im "echt"-Modus den "simuliert"-Lot NICHT
    zurückliefern (und umgekehrt) — sonst könnte ein "echt"-Fill gegen den
    "simuliert"-Lot desselben Titels gemittelt oder verrechnet werden."""
    engine = _make_engine()
    with Session(engine) as session:
        instrument_id, strategy_id = _seed_stammdaten(session)
        echt_lot = _make_position(
            instrument_id, strategy_id, menge=Decimal("10"), status="offen", mode="echt"
        )
        simuliert_lot = _make_position(
            instrument_id, strategy_id, menge=Decimal("5"), status="offen", mode="simuliert"
        )
        session.add(echt_lot)
        session.add(simuliert_lot)
        session.commit()

        repository = SqlAlchemyPositionRepository(session)
        echt_lots = repository.offene_positionen(str(instrument_id), mode="echt")
        simuliert_lots = repository.offene_positionen(str(instrument_id), mode="simuliert")

        assert [lot.position_id for lot in echt_lots] == [str(echt_lot.id)]
        assert [lot.position_id for lot in simuliert_lots] == [str(simuliert_lot.id)]


def test_lege_position_an_persistiert_kauf_mit_aufgeloester_strategie() -> None:
    """@trace depot#AC2,AC3,AC5 — legt eine neue offene Position mit dem
    (bereits gebühren-genetteten) Einstandspreis + Modus/Attribute aus dem
    Fill an; die Strategie wird über den Namen aufgelöst (FK)."""
    engine = _make_engine()
    with Session(engine) as session:
        instrument_id, _strategy_id = _seed_stammdaten(session)
        repository = SqlAlchemyPositionRepository(session)
        fill = _kauf_fill(instrument_id, menge=Decimal("10"))

        position_id = repository.lege_position_an(
            fill, einstand_preis=Decimal("101"), einstand_methode="gleitender_durchschnitt"
        )
        session.commit()

        position = session.get(Position, uuid.UUID(position_id))
        assert position is not None
        assert position.menge == Decimal("10")
        assert position.einstand_preis == Decimal("101")
        assert position.einstand_methode == "gleitender_durchschnitt"
        assert position.status == "offen"
        assert position.mode == "simuliert"
        assert position.these == "Langfristiger Index-Halter."


def test_lege_position_an_lehnt_unbekannte_strategie_ab() -> None:
    """@trace depot#AC2,AC3,AC5 — eine Strategie, die nicht als
    Stammdatenzeile existiert, kann keine Position anlegen (FK-
    Voraussetzung) — klarer Fehler statt stiller Inkonsistenz."""
    engine = _make_engine()
    with Session(engine) as session:
        instrument_id, _strategy_id = _seed_stammdaten(session)
        repository = SqlAlchemyPositionRepository(session)
        fill = _kauf_fill(instrument_id, strategie="Unbekannt")

        with pytest.raises(ValueError):
            repository.lege_position_an(
                fill, einstand_preis=Decimal("101"), einstand_methode="gleitender_durchschnitt"
            )


def test_aktualisiere_kauf_schreibt_menge_und_einstand_fort() -> None:
    """@trace depot#AC5 — ein Nachkauf (gleitender Durchschnitt) schreibt
    Menge + neuen Ø-Einstandspreis auf denselben Lot fort."""
    engine = _make_engine()
    with Session(engine) as session:
        instrument_id, strategy_id = _seed_stammdaten(session)
        position = _make_position(instrument_id, strategy_id, menge=Decimal("10"), status="offen")
        session.add(position)
        session.commit()

        repository = SqlAlchemyPositionRepository(session)
        repository.aktualisiere_kauf(
            str(position.id), neue_menge=Decimal("20"), neuer_einstand_preis=Decimal("111.5")
        )
        session.commit()

        aktualisiert = session.get(Position, position.id)
        assert aktualisiert.menge == Decimal("20")
        assert aktualisiert.einstand_preis == Decimal("111.5")


def test_verbuche_verkauf_lot_addiert_realisierten_gv_und_reduziert_menge() -> None:
    """@trace depot#AC2,AC3 — ein Teilverkauf reduziert die Menge und
    addiert den realisierten G/V-Anteil auf `realisierter_gv`, ohne den
    Lot zu schliessen."""
    engine = _make_engine()
    with Session(engine) as session:
        instrument_id, strategy_id = _seed_stammdaten(session)
        position = _make_position(instrument_id, strategy_id, menge=Decimal("10"), status="offen")
        session.add(position)
        session.commit()

        repository = SqlAlchemyPositionRepository(session)
        repository.verbuche_verkauf_lot(
            str(position.id), neue_menge=Decimal("6"), realisierter_gv_delta=Decimal("192")
        )
        session.commit()

        aktualisiert = session.get(Position, position.id)
        assert aktualisiert.menge == Decimal("6")
        assert aktualisiert.realisierter_gv == Decimal("192")
        assert aktualisiert.status == "offen"
        assert aktualisiert.closed_at is None


def test_verbuche_verkauf_lot_schliesst_position_bei_vollverkauf() -> None:
    """@trace depot#AC5 — reduziert ein Verkauf einen Lot auf Menge 0
    (Vollverkauf des Lots), wird er geschlossen (Status + `closed_at`)."""
    engine = _make_engine()
    with Session(engine) as session:
        instrument_id, strategy_id = _seed_stammdaten(session)
        position = _make_position(instrument_id, strategy_id, menge=Decimal("10"), status="offen")
        session.add(position)
        session.commit()

        repository = SqlAlchemyPositionRepository(session)
        repository.verbuche_verkauf_lot(
            str(position.id), neue_menge=Decimal("0"), realisierter_gv_delta=Decimal("190")
        )
        session.commit()

        aktualisiert = session.get(Position, position.id)
        assert aktualisiert.menge == Decimal("0")
        assert aktualisiert.status == "geschlossen"
        assert aktualisiert.closed_at is not None


def test_markiere_fill_verbucht_liefert_true_beim_ersten_mal() -> None:
    """@trace depot#AC2,AC3 — ADR-011/P8 (DBA-Zweit-Review S-016): eine
    noch nie gesehene `client_order_id` wird erfolgreich als verbucht
    markiert (`True`) und persistiert eine `depot_fill_dedup`-Zeile."""
    engine = _make_engine()
    with Session(engine) as session:
        instrument_id, _strategy_id = _seed_stammdaten(session)
        repository = SqlAlchemyPositionRepository(session)

        ergebnis = repository.markiere_fill_verbucht(
            "order-dedup-1", titel_id=str(instrument_id), richtung="kauf"
        )
        session.commit()

        assert ergebnis is True
        eintrag = session.get(DepotFillDedup, "order-dedup-1")
        assert eintrag is not None
        assert eintrag.instrument_id == instrument_id
        assert eintrag.richtung == "kauf"


def test_markiere_fill_verbucht_liefert_false_bei_wiederholung() -> None:
    """@trace depot#AC2,AC3 — ADR-011/P8 (DBA-Zweit-Review S-016): dieselbe
    `client_order_id` ein zweites Mal markieren (At-least-once-Zustellung
    dupliziert den Fill) liefert `False` — kein Crash, keine zweite Zeile."""
    engine = _make_engine()
    with Session(engine) as session:
        instrument_id, _strategy_id = _seed_stammdaten(session)
        repository = SqlAlchemyPositionRepository(session)

        erster = repository.markiere_fill_verbucht(
            "order-dedup-2", titel_id=str(instrument_id), richtung="verkauf"
        )
        session.commit()

        zweiter = repository.markiere_fill_verbucht(
            "order-dedup-2", titel_id=str(instrument_id), richtung="verkauf"
        )

        assert erster is True
        assert zweiter is False


def test_markiere_fill_verbucht_bleibt_retrybar_nach_rollback_der_transaktion() -> None:
    """@trace depot#AC2,AC3 — ADR-011 (DBA-Zweit-Review S-016, dokumentierte
    Invariante in `position_booking.verbuche_fill`): schlägt die eigentliche
    Positions-Mutation NACH einem erfolgreichen `markiere_fill_verbucht`
    fehl (z. B. `UnzureichenderBestandFehler`) und rollt der Aufrufer die
    GESAMTE Transaktion zurück statt zu committen, bleibt dieselbe
    `client_order_id` für einen legitimen Retry weiterhin verfügbar — der
    Marker wurde nie durabel (nur geflusht, nie committet)."""
    engine = _make_engine()
    with Session(engine) as session:
        instrument_id, _strategy_id = _seed_stammdaten(session)
        repository = SqlAlchemyPositionRepository(session)

        ergebnis = repository.markiere_fill_verbucht(
            "order-retry-1", titel_id=str(instrument_id), richtung="verkauf"
        )
        assert ergebnis is True

        session.rollback()  # simuliert: Aufrufer bricht die Gesamt-Transaktion ab

        retry = repository.markiere_fill_verbucht(
            "order-retry-1", titel_id=str(instrument_id), richtung="verkauf"
        )
        assert retry is True
