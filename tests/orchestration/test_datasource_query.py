"""Tests für die geteilte Datenquellen-Abfrage `app.orchestration.datasource_query`
(Story S-021).

Covers (dateneingang): AC7, AC8

- **AC7 ("eine Schnittstelle, drei Konsumenten"):**
  `test_hole_signal_buendel_liefert_identische_ergebnisse_je_konsumenten_kontext`
  belegt, dass `hole_signal_buendel()` für alle drei laut Spec genannten
  Konsumenten-Kontexte (neu/bestehend/research) exakt denselben Code-Pfad
  durchläuft — keine parallele Zweit-Implementierung je Konsument.
  `test_hole_signal_buendel_liefert_ein_buendel_je_titel_anfrage_in_reihenfolge`
  belegt, dass eine Batch-Anfrage mit mehreren Titeln über dieselbe
  Schnittstelle je Titel ein eigenes Bündel liefert (Reihenfolge erhalten).

- **AC8 (Registry-Auswahl + Aggregation, mindestens Liquidität + Volatilität):**
  `test_hole_signal_buendel_aggregiert_nur_aktive_registry_quellen_der_anlageklasse`
  belegt die Kern-Auswahl: nur Quellen, die die Registry der angefragten
  Anlageklasse zuordnet UND die aktiv sind, tragen zum Bündel bei; eine
  zugeordnete, aber inaktive Quelle wird ausgeschlossen.
  `test_hole_signal_buendel_ist_leer_ohne_registry_mapping_fuer_anlageklasse`
  und `test_hole_signal_buendel_ist_leer_ohne_gold_daten_fuer_titel` belegen
  das Fehlend-statt-geschätzt-Prinzip (analog AC2) für die beiden
  Leer-Fälle (keine Registry-Zuordnung / keine Gold-Historie).
  `test_provisorische_volatilitaet_ist_populations_standardabweichung`
  belegt die in `docs/specs/dateneingang.md` präzisierte, provisorische
  Berechnungsmethode konkret an bekannten Werten.

SQLite (in-memory) reicht aus — reine Lese-Aggregation über bereits
persistierte `MarketDataGold`-Zeilen, kein Postgres-spezifisches Konstrukt
involviert (analog `tests/db/test_gold.py`).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.contracts.dateneingang import SignalBuendelAnfrage, TitelAnfrage
from app.db.base import Base
from app.db.models import AssetClass, DataSource, DataSourceAssetClass, MarketDataGold
from app.orchestration.datasource_query import _provisorische_volatilitaet, hole_signal_buendel


@pytest.fixture()
def session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as db_session:
        db_session.add(AssetClass(id=1, name="Aktien", prio_stufe="MVP", aktiv=True))
        db_session.add(AssetClass(id=7, name="Krypto", prio_stufe="MVP", aktiv=True))
        db_session.commit()
        yield db_session


def _quelle(
    session: Session, *, name: str, aktiv: bool = True, kategorie: str = "equity_fundamentals"
) -> DataSource:
    quelle = DataSource(
        id=uuid.uuid4(),
        name=name,
        kategorie=kategorie,
        qualitaet="hoch",
        frequenz_sekunden=60,
        aktiv=aktiv,
    )
    session.add(quelle)
    session.commit()
    return quelle


def _mappe_anlageklasse(session: Session, *, quelle: DataSource, anlageklasse: int) -> None:
    session.add(DataSourceAssetClass(data_source_id=quelle.id, asset_class_id=anlageklasse))
    session.commit()


def _gold_zeile(
    session: Session,
    *,
    quelle: DataSource,
    symbol: str,
    wert: str,
    observed_at: datetime,
    qualitaetsindikator: str = "hoch",
) -> MarketDataGold:
    zeile = MarketDataGold(
        silver_id=uuid.uuid4(),
        silver_observed_at=observed_at,
        data_source_id=quelle.id,
        source_event_id=f"{quelle.name}:{symbol}:{observed_at.isoformat()}",
        symbol=symbol,
        angereicherter_wert=Decimal(wert),
        qualitaetsindikator=qualitaetsindikator,
        observed_at=observed_at,
    )
    session.add(zeile)
    session.commit()
    return zeile


def test_hole_signal_buendel_aggregiert_nur_aktive_registry_quellen_der_anlageklasse(
    session: Session,
) -> None:
    """@trace dateneingang#AC8 — nur Registry-Quellen, die der angefragten
    Anlageklasse zugeordnet UND aktiv sind, tragen Signale bei; eine
    zugeordnete, aber inaktive Quelle wird ausgeschlossen (kein Abruf/keine
    Aggregation aus deaktivierten Quellen)."""
    quelle_a = _quelle(session, name="IBKR")
    quelle_b = _quelle(session, name="Yahoo Finance")
    quelle_inaktiv = _quelle(session, name="Institutionell (inaktiv)", aktiv=False)
    for quelle in (quelle_a, quelle_b, quelle_inaktiv):
        _mappe_anlageklasse(session, quelle=quelle, anlageklasse=1)

    _gold_zeile(
        session,
        quelle=quelle_a,
        symbol="AAPL",
        wert="400",
        observed_at=datetime(2026, 1, 1, tzinfo=UTC),
    )
    _gold_zeile(
        session,
        quelle=quelle_b,
        symbol="AAPL",
        wert="410",
        observed_at=datetime(2026, 1, 1, tzinfo=UTC),
    )
    # Waere die inaktive Quelle faelschlich beruecksichtigt worden, gaebe es
    # hier ohnehin keine Gold-Zeile (Ingest respektiert den Toggle) — der
    # Test belegt trotzdem die explizite Filterung in `_passende_quellen`.

    [buendel] = hole_signal_buendel(
        session,
        SignalBuendelAnfrage(
            titel_anfragen=[TitelAnfrage(titel="AAPL", anlageklasse=1)],
            konsumenten_kontext="neu",
        ),
    )

    quellen_namen = {metadatum.name for metadatum in buendel.quellen_metadaten}
    assert quellen_namen == {"IBKR", "Yahoo Finance"}
    assert len(buendel.signale) == 2
    assert buendel.liquiditaet == Decimal(2)
    assert buendel.volatilitaet is not None
    assert buendel.titel == "AAPL"
    assert buendel.anlageklasse == 1


def test_hole_signal_buendel_ist_leer_ohne_registry_mapping_fuer_anlageklasse(
    session: Session,
) -> None:
    """@trace dateneingang#AC8 — hat keine Quelle die angefragte Anlageklasse
    zugeordnet, ist das Bündel strukturell leer (kein geschätzter Wert)."""
    [buendel] = hole_signal_buendel(
        session,
        SignalBuendelAnfrage(
            titel_anfragen=[TitelAnfrage(titel="BTC", anlageklasse=7)],
            konsumenten_kontext="research",
        ),
    )

    assert buendel.signale == []
    assert buendel.liquiditaet is None
    assert buendel.volatilitaet is None
    assert buendel.quellen_metadaten == []


def test_hole_signal_buendel_ist_leer_ohne_gold_daten_fuer_titel(session: Session) -> None:
    """@trace dateneingang#AC8 — eine der Anlageklasse zugeordnete, aktive
    Quelle ohne persistierte Gold-Daten für GENAU diesen Titel trägt nichts
    bei; das Bündel bleibt leer statt geschätzt."""
    quelle = _quelle(session, name="IBKR")
    _mappe_anlageklasse(session, quelle=quelle, anlageklasse=1)
    _gold_zeile(
        session,
        quelle=quelle,
        symbol="MSFT",
        wert="300",
        observed_at=datetime(2026, 1, 1, tzinfo=UTC),
    )

    [buendel] = hole_signal_buendel(
        session,
        SignalBuendelAnfrage(
            titel_anfragen=[TitelAnfrage(titel="AAPL", anlageklasse=1)],
            konsumenten_kontext="bestehend",
        ),
    )

    assert buendel.signale == []
    assert buendel.liquiditaet is None
    assert buendel.volatilitaet is None


def test_hole_signal_buendel_signal_traegt_neuesten_wert_und_qualitaetsindikator(
    session: Session,
) -> None:
    """@trace dateneingang#AC8 — pro Quelle fliesst der ZEITLICH NEUESTE
    Gold-Datenpunkt in `signale` ein (aktuelles Signal je Quelle), nicht ein
    beliebiger historischer."""
    quelle = _quelle(session, name="IBKR")
    _mappe_anlageklasse(session, quelle=quelle, anlageklasse=1)
    _gold_zeile(
        session,
        quelle=quelle,
        symbol="AAPL",
        wert="400",
        observed_at=datetime(2026, 1, 1, tzinfo=UTC),
        qualitaetsindikator="mittel",
    )
    _gold_zeile(
        session,
        quelle=quelle,
        symbol="AAPL",
        wert="420",
        observed_at=datetime(2026, 1, 3, tzinfo=UTC),
        qualitaetsindikator="hoch",
    )

    [buendel] = hole_signal_buendel(
        session,
        SignalBuendelAnfrage(
            titel_anfragen=[TitelAnfrage(titel="AAPL", anlageklasse=1)],
            konsumenten_kontext="neu",
        ),
    )

    [signal] = buendel.signale
    assert signal.wert == Decimal("420")
    assert signal.qualitaetsindikator == "hoch"


def test_hole_signal_buendel_liefert_identische_ergebnisse_je_konsumenten_kontext(
    session: Session,
) -> None:
    """@trace dateneingang#AC7 — Suchkriteria (neu), Depot-Suchkriterien
    (bestehend) und Research (research) erhalten für dieselbe Titel-Anfrage
    identische Ergebnisse über dieselbe Schnittstelle — keine parallele
    Zweit-Implementierung je Konsumenten-Kontext."""
    quelle = _quelle(session, name="IBKR")
    _mappe_anlageklasse(session, quelle=quelle, anlageklasse=1)
    _gold_zeile(
        session,
        quelle=quelle,
        symbol="AAPL",
        wert="400",
        observed_at=datetime(2026, 1, 1, tzinfo=UTC),
    )

    ergebnisse = {
        kontext: hole_signal_buendel(
            session,
            SignalBuendelAnfrage(
                titel_anfragen=[TitelAnfrage(titel="AAPL", anlageklasse=1)],
                konsumenten_kontext=kontext,
            ),
        )[0]
        for kontext in ("neu", "bestehend", "research")
    }

    referenz = ergebnisse["neu"]
    for kontext in ("bestehend", "research"):
        andere = ergebnisse[kontext]
        assert andere.signale == referenz.signale
        assert andere.liquiditaet == referenz.liquiditaet
        assert andere.volatilitaet == referenz.volatilitaet
        assert andere.quellen_metadaten == referenz.quellen_metadaten


def test_hole_signal_buendel_liefert_ein_buendel_je_titel_anfrage_in_reihenfolge(
    session: Session,
) -> None:
    """@trace dateneingang#AC7,AC8 — eine gebündelte Batch-Anfrage (mehrere
    Titel in einer Anfrage, vgl. `docs/specs/depot-ueberwachung.md` "stellt
    gebündelt eine Abfrage je Titel") liefert je Titel-Anfrage genau ein
    Bündel, in derselben Reihenfolge wie im Input."""
    quelle_aktien = _quelle(session, name="IBKR", kategorie="equity_fundamentals")
    quelle_krypto = _quelle(session, name="On-Chain-Feed", kategorie="blockchain_crypto")
    _mappe_anlageklasse(session, quelle=quelle_aktien, anlageklasse=1)
    _mappe_anlageklasse(session, quelle=quelle_krypto, anlageklasse=7)
    _gold_zeile(
        session,
        quelle=quelle_aktien,
        symbol="AAPL",
        wert="400",
        observed_at=datetime(2026, 1, 1, tzinfo=UTC),
    )
    _gold_zeile(
        session,
        quelle=quelle_krypto,
        symbol="BTC",
        wert="60000",
        observed_at=datetime(2026, 1, 1, tzinfo=UTC),
    )

    buendel_liste = hole_signal_buendel(
        session,
        SignalBuendelAnfrage(
            titel_anfragen=[
                TitelAnfrage(titel="AAPL", anlageklasse=1),
                TitelAnfrage(titel="BTC", anlageklasse=7),
            ],
            konsumenten_kontext="research",
        ),
    )

    assert [buendel.titel for buendel in buendel_liste] == ["AAPL", "BTC"]
    assert buendel_liste[0].signale[0].wert == Decimal("400")
    assert buendel_liste[1].signale[0].wert == Decimal("60000")


def test_provisorische_volatilitaet_ist_populations_standardabweichung() -> None:
    """@trace dateneingang#AC8 — belegt die in `docs/specs/dateneingang.md`
    präzisierte provisorische Berechnungsmethode konkret: `None` ohne
    Datenpunkte, `0` bei genau einem Datenpunkt (Streuung per Definition 0),
    sonst die Populationsstandardabweichung."""
    assert _provisorische_volatilitaet([]) is None
    assert _provisorische_volatilitaet([Decimal("100")]) == Decimal("0")
    assert _provisorische_volatilitaet([Decimal("100"), Decimal("100")]) == Decimal("0")

    ergebnis = _provisorische_volatilitaet(
        [
            Decimal("2"),
            Decimal("4"),
            Decimal("4"),
            Decimal("4"),
            Decimal("5"),
            Decimal("5"),
            Decimal("7"),
            Decimal("9"),
        ]
    )
    # bekanntes Lehrbuch-Beispiel: Populationsstandardabweichung dieser Reihe ist 2.0.
    assert ergebnis == Decimal("2.0")
