"""Tests für `SqlAlchemyPositionRepository` (Story S-015 + S-016 + S-016
DBA-Zweit-Review).

Covers (depot): AC10, AC2, AC3, AC5, AC4, AC7, AC8, AC9, AC6

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

S-035 (AC4/AC7) ergänzt `schreibe_transaktion` (append-only Insert in die
`transaction`-Historie inkl. Arrival-Price/Slippage) und
`historie_je_titel` (chronologisch sortierte, Mode-isolierte Lesesicht,
Grundlage der TCA je Trade + aggregiert).

S-036 (AC8/AC9) ergänzt `alle_offenen_positionen` (depotweite,
mode-isolierte Sicht über ALLE Titel hinweg, inkl. Anlageklasse,
GICS-Branche, Strategie-Name und Exit-Regeln — Basis für
`app.domain.portfolio.portfolio_aggregate`).

S-053 (AC6, FX-Attribution) ergänzt: `lege_position_an`/`aktualisiere_kauf`
persistieren `Position.einstand_fx_rate`, `offene_positionen` liefert ihn
zurück, und `schreibe_transaktion` persistiert bei gesetztem `fx_split`
zusätzlich `Transaction.fx_rate`/`kapital_gv_chf`/`waehrungs_gv_chf`
(→ BR-129).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.adapters.repositories.position_repository import SqlAlchemyPositionRepository
from app.contracts.depot import ExitRegeln, FillInput
from app.db.base import Base
from app.db.models import (
    AssetClass,
    DepotFillDedup,
    ExitRule,
    Instrument,
    Position,
    Strategy,
    TimeHorizon,
)
from app.domain.portfolio.fx_attribution import FxSplit


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


def _naiv(zeitpunkt: datetime) -> datetime:
    """SQLite (Struktur-Tests, In-Memory) rundet `DateTime(timezone=True)`
    beim Roundtrip auf naive `datetime`-Werte ab (bekannte SQLAlchemy/
    SQLite-Einschränkung) — Vergleiche gegen einen ursprünglich tz-aware
    Erwartungswert müssen diesen daher ebenfalls entkernen."""
    return zeitpunkt.replace(tzinfo=None)


def _verkauf_fill(instrument_id: uuid.UUID, **overrides: object) -> FillInput:
    kwargs = {
        "client_order_id": "order-verkauf-1",
        "titel_id": str(instrument_id),
        "anlageklasse": 1,
        "gics_branche": "Technology",
        "richtung": "verkauf",
        "menge": Decimal("5"),
        "fill_preis": Decimal("120"),
        "kosten": Decimal("5"),
        "arrival_price": Decimal("119"),
        "waehrung": "CHF",
        "zeitstempel": datetime(2026, 7, 12, 11, 0, tzinfo=UTC),
        "mode": "simuliert",
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


# --- S-035: append-only Transaktionshistorie & TCA (AC4/AC7) --------------


def test_schreibe_transaktion_persistiert_alle_ac4_felder() -> None:
    """@trace depot#AC4 — ein Fill wird mit Titel, Richtung, Menge,
    Fill-Preis, Kosten, Zeitstempel und Währung in die Historie
    geschrieben."""
    engine = _make_engine()
    with Session(engine) as session:
        instrument_id, _strategy_id = _seed_stammdaten(session)
        repository = SqlAlchemyPositionRepository(session)
        fill = _kauf_fill(instrument_id, menge=Decimal("10"), fill_preis=Decimal("100"))

        repository.schreibe_transaktion(fill, position_id=None)
        session.commit()

        historie = repository.historie_je_titel(str(instrument_id), mode="simuliert")
        assert len(historie) == 1
        eintrag = historie[0]
        assert eintrag.titel_id == str(instrument_id)
        assert eintrag.richtung == "kauf"
        assert eintrag.menge == Decimal("10")
        assert eintrag.fill_preis == Decimal("100")
        assert eintrag.kosten == fill.kosten
        assert eintrag.waehrung == "CHF"
        assert eintrag.zeitstempel == _naiv(fill.zeitstempel)


def test_schreibe_transaktion_speichert_arrival_price_und_slippage() -> None:
    """@trace depot#AC7 — Arrival-Price + die daraus berechnete realisierte
    Slippage (Fill-Preis − Arrival-Price) werden je Trade gespeichert."""
    engine = _make_engine()
    with Session(engine) as session:
        instrument_id, _strategy_id = _seed_stammdaten(session)
        repository = SqlAlchemyPositionRepository(session)
        fill = _kauf_fill(instrument_id, fill_preis=Decimal("101.5"), arrival_price=Decimal("100"))

        repository.schreibe_transaktion(fill, position_id=None)
        session.commit()

        eintrag = repository.historie_je_titel(str(instrument_id), mode="simuliert")[0]
        assert eintrag.arrival_price == Decimal("100")
        assert eintrag.slippage == Decimal("1.5")


def test_schreibe_transaktion_akzeptiert_verkauf_ohne_eindeutige_position_id() -> None:
    """@trace depot#AC4 — ein Verkauf-Fill, der bei FIFO mehreren Lots
    zugeordnet werden könnte, kann trotzdem ohne `position_id` (NULL)
    historisiert werden — die append-only Historie selbst verlangt keine
    eindeutige Lot-Zuordnung (Verträge-Vertrag referenziert nur
    `titel_id`)."""
    engine = _make_engine()
    with Session(engine) as session:
        instrument_id, _strategy_id = _seed_stammdaten(session)
        repository = SqlAlchemyPositionRepository(session)
        fill = _verkauf_fill(instrument_id)

        repository.schreibe_transaktion(fill, position_id=None)
        session.commit()

        eintrag = repository.historie_je_titel(str(instrument_id), mode="simuliert")[0]
        assert eintrag.richtung == "verkauf"


def test_historie_je_titel_ist_leer_ohne_gebuchte_fills() -> None:
    """@trace depot#AC4,AC7 — kein gebuchter Fill für einen Titel ergibt
    eine leere Historie, keinen Fehler."""
    engine = _make_engine()
    with Session(engine) as session:
        instrument_id, _strategy_id = _seed_stammdaten(session)
        repository = SqlAlchemyPositionRepository(session)
        assert repository.historie_je_titel(str(instrument_id), mode="simuliert") == []


def test_historie_je_titel_sortiert_chronologisch_aufsteigend() -> None:
    """@trace depot#AC4,AC7 — mehrere Einträge desselben Titels sind
    aufsteigend nach Zeitstempel sortiert (Grundlage für TCA-Auswertung je
    Trade in der richtigen Reihenfolge)."""
    engine = _make_engine()
    with Session(engine) as session:
        instrument_id, _strategy_id = _seed_stammdaten(session)
        repository = SqlAlchemyPositionRepository(session)
        spaeter = _kauf_fill(
            instrument_id,
            client_order_id="order-spaeter",
            zeitstempel=datetime(2026, 7, 12, 15, 0, tzinfo=UTC),
        )
        frueher = _kauf_fill(
            instrument_id,
            client_order_id="order-frueher",
            zeitstempel=datetime(2026, 7, 12, 9, 0, tzinfo=UTC),
        )
        # Absichtlich in "falscher" Reihenfolge geschrieben, um die
        # `ORDER BY booked_at`-Sortierung zu erzwingen.
        repository.schreibe_transaktion(spaeter, position_id=None)
        repository.schreibe_transaktion(frueher, position_id=None)
        session.commit()

        historie = repository.historie_je_titel(str(instrument_id), mode="simuliert")
        assert [e.zeitstempel for e in historie] == [
            _naiv(frueher.zeitstempel),
            _naiv(spaeter.zeitstempel),
        ]


def test_historie_je_titel_filtert_nach_modus() -> None:
    """@trace depot#AC4,AC7 — Mode-Isolation (BR-130, analog zu
    `offene_positionen`/`aktuelle_menge`): ein "echt"-Fill erscheint nicht
    in der "simuliert"-Historie desselben Titels (und umgekehrt)."""
    engine = _make_engine()
    with Session(engine) as session:
        instrument_id, _strategy_id = _seed_stammdaten(session)
        repository = SqlAlchemyPositionRepository(session)
        echt_fill = _kauf_fill(instrument_id, client_order_id="order-echt", mode="echt")
        simuliert_fill = _kauf_fill(
            instrument_id, client_order_id="order-simuliert", mode="simuliert"
        )
        repository.schreibe_transaktion(echt_fill, position_id=None)
        repository.schreibe_transaktion(simuliert_fill, position_id=None)
        session.commit()

        echt_historie = repository.historie_je_titel(str(instrument_id), mode="echt")
        simuliert_historie = repository.historie_je_titel(str(instrument_id), mode="simuliert")

        assert len(echt_historie) == 1
        assert len(simuliert_historie) == 1
        assert echt_historie[0].zeitstempel == _naiv(echt_fill.zeitstempel)
        assert simuliert_historie[0].zeitstempel == _naiv(simuliert_fill.zeitstempel)


# --- S-036: depotweite Positions-Sicht (AC8/AC9) ---------------------------


def _seed_instrument(
    session: Session, *, asset_class_id: int, gics_sector: str | None, symbol: str
) -> uuid.UUID:
    instrument = Instrument(
        id=uuid.uuid4(),
        symbol=symbol,
        name=f"{symbol} Inc",
        asset_class_id=asset_class_id,
        gics_sector=gics_sector,
        currency="CHF",
    )
    session.add(instrument)
    session.commit()
    return instrument.id


def test_alle_offenen_positionen_ist_leer_ohne_bestand() -> None:
    """@trace depot#AC8,AC9 — kein offener Lot in keinem Titel ergibt eine
    leere Liste, keinen Fehler."""
    engine = _make_engine()
    with Session(engine) as session:
        _seed_stammdaten(session)
        repository = SqlAlchemyPositionRepository(session)
        assert repository.alle_offenen_positionen(mode="simuliert") == []


def test_alle_offenen_positionen_liefert_attribute_ueber_alle_titel() -> None:
    """@trace depot#AC8 — die depotweite Sicht liefert Anlageklasse,
    GICS-Branche, Menge, Einstandspreis und Strategie über MEHRERE Titel
    hinweg (nicht nur einen wie `offene_positionen`)."""
    engine = _make_engine()
    with Session(engine) as session:
        _seed_stammdaten(session)
        strategy_id = session.scalars(select(Strategy.id)).first()
        instrument_a = _seed_instrument(
            session, asset_class_id=1, gics_sector="Technology", symbol="TECH"
        )
        instrument_b = _seed_instrument(
            session, asset_class_id=1, gics_sector="Healthcare", symbol="PHARMA"
        )
        session.add(_make_position(instrument_a, strategy_id, menge=Decimal("10"), status="offen"))
        session.add(_make_position(instrument_b, strategy_id, menge=Decimal("4"), status="offen"))
        session.commit()

        repository = SqlAlchemyPositionRepository(session)
        bestand = repository.alle_offenen_positionen(mode="simuliert")

        titel_ids = {p.titel_id for p in bestand}
        assert titel_ids == {str(instrument_a), str(instrument_b)}
        eintrag_a = next(p for p in bestand if p.titel_id == str(instrument_a))
        assert eintrag_a.asset_class_id == 1
        assert eintrag_a.gics_branche == "Technology"
        assert eintrag_a.menge == Decimal("10")
        assert eintrag_a.einstand_preis == Decimal("100")
        assert eintrag_a.strategie == "Index"
        eintrag_b = next(p for p in bestand if p.titel_id == str(instrument_b))
        assert eintrag_b.gics_branche == "Healthcare"


def test_alle_offenen_positionen_ignoriert_geschlossene_positionen() -> None:
    """@trace depot#AC8 — eine geschlossene Position fliesst nicht in die
    depotweite Sicht ein."""
    engine = _make_engine()
    with Session(engine) as session:
        instrument_id, strategy_id = _seed_stammdaten(session)
        session.add(
            _make_position(instrument_id, strategy_id, menge=Decimal("0"), status="geschlossen")
        )
        session.commit()

        repository = SqlAlchemyPositionRepository(session)
        assert repository.alle_offenen_positionen(mode="simuliert") == []


def test_alle_offenen_positionen_filtert_nach_modus() -> None:
    """@trace depot#AC8,AC9 — Mode-Isolation (BR-113/BR-130): ein "echt"-
    Lot erscheint nicht in der "simuliert"-Sicht (und umgekehrt)."""
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
                instrument_id, strategy_id, menge=Decimal("5"), status="offen", mode="simuliert"
            )
        )
        session.commit()

        repository = SqlAlchemyPositionRepository(session)
        echt_bestand = repository.alle_offenen_positionen(mode="echt")
        simuliert_bestand = repository.alle_offenen_positionen(mode="simuliert")

        assert [p.menge for p in echt_bestand] == [Decimal("10")]
        assert [p.menge for p in simuliert_bestand] == [Decimal("5")]


def test_alle_offenen_positionen_liefert_none_exit_regeln_ohne_exit_rule_zeile() -> None:
    """@trace depot#AC9 — solange keine `exit_rule`-Zeile existiert (kein
    Aufrufer legt bislang eine an, S-037/S-038), sind alle Exit-Regel-Felder
    `None` statt eines Fehlers/einer Fiktion."""
    engine = _make_engine()
    with Session(engine) as session:
        instrument_id, strategy_id = _seed_stammdaten(session)
        session.add(_make_position(instrument_id, strategy_id, menge=Decimal("10"), status="offen"))
        session.commit()

        repository = SqlAlchemyPositionRepository(session)
        eintrag = repository.alle_offenen_positionen(mode="simuliert")[0]

        assert eintrag.exit_regeln.stop_loss_pct is None
        assert eintrag.exit_regeln.take_profit_pct is None
        assert eintrag.exit_regeln.stop_typ is None
        assert eintrag.exit_regeln.atr_multiplikator is None
        assert eintrag.exit_regeln.thesis_invalidation is None
        assert eintrag.exit_regeln.time_box is None


def test_alle_offenen_positionen_liefert_gesetzte_exit_regeln() -> None:
    """@trace depot#AC9 — existiert eine `exit_rule`-Zeile für den Lot,
    liefert die depotweite Sicht die beim Kauf fixierten Werte (die beim
    Kauf fixierten Werte, unverändert über die Haltedauer)."""
    engine = _make_engine()
    with Session(engine) as session:
        instrument_id, strategy_id = _seed_stammdaten(session)
        position = _make_position(instrument_id, strategy_id, menge=Decimal("10"), status="offen")
        session.add(position)
        session.commit()
        session.add(
            ExitRule(
                position_id=position.id,
                stop_loss_pct=Decimal("-15"),
                take_profit_pct=Decimal("30"),
                stop_typ="fix_pct",
                atr_multiplikator=None,
                thesis_invalidation="Marktanteil < 10%",
                time_box=None,
            )
        )
        session.commit()

        repository = SqlAlchemyPositionRepository(session)
        eintrag = repository.alle_offenen_positionen(mode="simuliert")[0]

        assert eintrag.exit_regeln.stop_loss_pct == Decimal("-15")
        assert eintrag.exit_regeln.take_profit_pct == Decimal("30")
        assert eintrag.exit_regeln.stop_typ == "fix_pct"
        assert eintrag.exit_regeln.thesis_invalidation == "Marktanteil < 10%"


def test_alle_offenen_positionen_sortiert_nach_titel_und_opened_at() -> None:
    """@trace depot#AC9 — aufsteigend nach `instrument_id`, `opened_at`
    sortiert: bei mehreren Lots desselben Titels (FIFO) steht der älteste
    zuerst — Voraussetzung für die Titel-Dedup-Logik in
    `app.domain.portfolio.portfolio_aggregate
    .ermittle_titel_strategie_exit_regeln`."""
    engine = _make_engine()
    with Session(engine) as session:
        instrument_id, strategy_id = _seed_stammdaten(session)
        aelterer = _make_position(instrument_id, strategy_id, menge=Decimal("10"), status="offen")
        aelterer.opened_at = datetime(2026, 1, 1, tzinfo=UTC)
        juengerer = _make_position(instrument_id, strategy_id, menge=Decimal("5"), status="offen")
        juengerer.opened_at = datetime(2026, 6, 1, tzinfo=UTC)
        session.add(juengerer)
        session.add(aelterer)
        session.commit()

        repository = SqlAlchemyPositionRepository(session)
        bestand = repository.alle_offenen_positionen(mode="simuliert")
        assert [p.position_id for p in bestand] == [str(aelterer.id), str(juengerer.id)]


# --- S-053: FX-Attribution (AC6, deckt A3) ---------------------------------


def test_lege_position_an_persistiert_einstand_fx_rate() -> None:
    """@trace depot#AC6 — ein Fremdwährungs-Kauf persistiert den
    Ø-Einstands-FX-Kurs auf dem neuen Lot."""
    engine = _make_engine()
    with Session(engine) as session:
        instrument_id, _strategy_id = _seed_stammdaten(session)
        repository = SqlAlchemyPositionRepository(session)
        fill = _kauf_fill(instrument_id, waehrung="USD", fx_rate=Decimal("0.90"))

        position_id = repository.lege_position_an(
            fill,
            einstand_preis=Decimal("101"),
            einstand_methode="gleitender_durchschnitt",
            einstand_fx_rate=Decimal("0.90"),
        )
        session.commit()

        position = session.get(Position, uuid.UUID(position_id))
        assert position.einstand_fx_rate == Decimal("0.90")


def test_lege_position_an_ohne_fx_rate_bleibt_einstand_fx_rate_none() -> None:
    """@trace depot#AC6 — ein CHF-Kauf lässt `einstand_fx_rate` `None`
    (keine Attribution nötig)."""
    engine = _make_engine()
    with Session(engine) as session:
        instrument_id, _strategy_id = _seed_stammdaten(session)
        repository = SqlAlchemyPositionRepository(session)
        fill = _kauf_fill(instrument_id)

        position_id = repository.lege_position_an(
            fill, einstand_preis=Decimal("101"), einstand_methode="gleitender_durchschnitt"
        )
        session.commit()

        position = session.get(Position, uuid.UUID(position_id))
        assert position.einstand_fx_rate is None


def test_aktualisiere_kauf_schreibt_einstand_fx_rate_fort() -> None:
    """@trace depot#AC6 — ein Nachkauf schreibt den (bereits gemittelten)
    neuen Ø-Einstands-FX-Kurs auf denselben Lot fort."""
    engine = _make_engine()
    with Session(engine) as session:
        instrument_id, strategy_id = _seed_stammdaten(session)
        position = _make_position(instrument_id, strategy_id, menge=Decimal("10"), status="offen")
        session.add(position)
        session.commit()

        repository = SqlAlchemyPositionRepository(session)
        repository.aktualisiere_kauf(
            str(position.id),
            neue_menge=Decimal("20"),
            neuer_einstand_preis=Decimal("111.5"),
            einstand_fx_rate=Decimal("0.95"),
        )
        session.commit()

        aktualisiert = session.get(Position, position.id)
        assert aktualisiert.einstand_fx_rate == Decimal("0.95")


def test_offene_positionen_liefert_einstand_fx_rate() -> None:
    """@trace depot#AC6 — `offene_positionen` liefert den persistierten
    Ø-Einstands-FX-Kurs zurück (Grundlage für die realisierte
    FX-Attribution bei einem späteren Verkauf)."""
    engine = _make_engine()
    with Session(engine) as session:
        instrument_id, strategy_id = _seed_stammdaten(session)
        position = _make_position(instrument_id, strategy_id, menge=Decimal("10"), status="offen")
        position.einstand_fx_rate = Decimal("0.90")
        session.add(position)
        session.commit()

        repository = SqlAlchemyPositionRepository(session)
        lots = repository.offene_positionen(str(instrument_id), mode="simuliert")
        assert lots[0].einstand_fx_rate == Decimal("0.90")


def test_schreibe_transaktion_persistiert_fx_rate_ohne_fx_split_bei_kauf() -> None:
    """@trace depot#AC6 — ein Fremdwährungs-Kauf speichert `fx_rate` als
    Referenzwert, aber KEIN `kapital_gv_chf`/`waehrungs_gv_chf` (kein G/V
    auf einen Kauf)."""
    engine = _make_engine()
    with Session(engine) as session:
        instrument_id, _strategy_id = _seed_stammdaten(session)
        repository = SqlAlchemyPositionRepository(session)
        fill = _kauf_fill(instrument_id, waehrung="USD", fx_rate=Decimal("0.90"))

        repository.schreibe_transaktion(fill, position_id=None, fx_split=None)
        session.commit()

        eintrag = repository.historie_je_titel(str(instrument_id), mode="simuliert")[0]
        assert eintrag.fx_rate == Decimal("0.90")
        assert eintrag.kapital_gv_chf is None
        assert eintrag.waehrungs_gv_chf is None


def test_schreibe_transaktion_persistiert_fx_split_bei_verkauf() -> None:
    """@trace depot#AC6 — ein Fremdwährungs-Verkauf mit gesetztem
    `fx_split` persistiert `kapital_gv_chf`/`waehrungs_gv_chf` zusätzlich
    zu `fx_rate`."""
    engine = _make_engine()
    with Session(engine) as session:
        instrument_id, _strategy_id = _seed_stammdaten(session)
        repository = SqlAlchemyPositionRepository(session)
        fill = _verkauf_fill(instrument_id, waehrung="USD", fx_rate=Decimal("0.95"))
        fx_split = FxSplit(kapital_gv_chf=Decimal("175.5"), waehrungs_gv_chf=Decimal("59.75"))

        repository.schreibe_transaktion(fill, position_id=None, fx_split=fx_split)
        session.commit()

        eintrag = repository.historie_je_titel(str(instrument_id), mode="simuliert")[0]
        assert eintrag.fx_rate == Decimal("0.95")
        assert eintrag.kapital_gv_chf == Decimal("175.5")
        assert eintrag.waehrungs_gv_chf == Decimal("59.75")


def test_schreibe_transaktion_chf_hat_keinen_fx_rate() -> None:
    """@trace depot#AC6 — ein CHF-Fill bleibt bei `fx_rate`/`kapital_gv_chf`/
    `waehrungs_gv_chf` durchgängig `None`."""
    engine = _make_engine()
    with Session(engine) as session:
        instrument_id, _strategy_id = _seed_stammdaten(session)
        repository = SqlAlchemyPositionRepository(session)
        fill = _kauf_fill(instrument_id)

        repository.schreibe_transaktion(fill, position_id=None)
        session.commit()

        eintrag = repository.historie_je_titel(str(instrument_id), mode="simuliert")[0]
        assert eintrag.fx_rate is None
        assert eintrag.kapital_gv_chf is None
        assert eintrag.waehrungs_gv_chf is None
