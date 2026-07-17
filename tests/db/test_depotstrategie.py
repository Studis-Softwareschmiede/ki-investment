"""Tests fuer die Depotstrategie-Logik `app/db/depotstrategie.py` (Story
S-043).

Covers (risikomanagement): AC1, AC3, AC4, AC11

- AC3 (3 Presets, Nutzer wählt + justiert fein): `waehle_risikoprofil_
  preset()` — Aktivierung eines Presets, Umschalten zwischen Presets lässt
  genau eine Zeile aktiv (BR-117, App-seitige Durchsetzung), Fehlerfall
  unbekanntes Profil. `passe_depotstrategie_an()` — Feinjustierung
  einzelner Werte ohne die übrigen zu verändern, Fehlerfall unbekannte
  Depotstrategie-ID. `setze_klassen_limit()` — Anlegen + Aktualisieren
  (Upsert) eines Klassen-Limits.
- AC1 (Grenzwert-Regelwerk vollständig lesbar): `lade_aktive_
  depotstrategie()` liefert alle AC1-Grenzwerte (Einzelposition, Sektor,
  Cash-Quote, Klassen-Limits) der aktiven Depotstrategie.
- AC4 (Preset-Defaults korrekt aktivierbar): die per Migration geseedeten
  Preset-Werte werden über `waehle_risikoprofil_preset()` +
  `lade_aktive_depotstrategie()` unverändert sichtbar.
- AC11 (Gate bezieht Limits ausschliesslich aus der Depotstrategie):
  `lade_aktive_depotstrategie()` ist der einzige geprüfte Lesepfad; ohne
  aktive Depotstrategie liefert er `None` (kein Grenzwert verfügbar).
"""

from __future__ import annotations

import uuid
from decimal import Decimal

import pytest
from sqlalchemy import create_engine, select, text
from sqlalchemy.orm import Session

from app.db.base import Base
from app.db.depotstrategie import (
    DepotstrategieNichtGefundenError,
    RisikoprofilNichtGefundenError,
    lade_aktive_depotstrategie,
    passe_depotstrategie_an,
    setze_klassen_limit,
    waehle_risikoprofil_preset,
)
from app.db.models import AssetClass, PortfolioClassLimit, PortfolioStrategy, RiskProfile

KRYPTO_ID = 7


def _engine_mit_presets(*, mit_partiellem_aktiv_index: bool = False) -> Session:
    """Baut eine SQLite-Session mit den 3 Risikoprofilen + je einer
    Preset-`PortfolioStrategy`-Zeile (Werte analog dem Migrations-Seed,
    hier bewusst unabhängig nachgebaut statt importiert — reine
    Fixture-Daten für die App-Layer-Logik, kein Migrations-Test).

    `mit_partiellem_aktiv_index=True` legt zusätzlich den partiellen
    Unique-Index `ux_portfolio_strategy_aktiv` (WHERE aktiv) an — er steht
    bewusst NUR in der rohen Migrations-DDL, nicht im ORM-`__table_args__`,
    weshalb `Base.metadata.create_all` ihn sonst nicht erzeugt. SQLite
    unterstützt `CREATE UNIQUE INDEX ... WHERE` wie Postgres, sodass das
    BR-117-Laufzeitverhalten gegen den ECHTEN Index prüfbar wird."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session = Session(engine)
    if mit_partiellem_aktiv_index:
        session.execute(
            text(
                "CREATE UNIQUE INDEX ux_portfolio_strategy_aktiv "
                f"ON {PortfolioStrategy.__tablename__} (aktiv) WHERE aktiv"
            )
        )
    session.add(AssetClass(id=KRYPTO_ID, name="Kryptowährungen", prio_stufe="Stufe3", aktiv=True))

    presets = {
        "konservativ": {"einzel": "2", "krypto": "5"},
        "ausgewogen": {"einzel": "5", "krypto": "10"},
        "offensiv": {"einzel": "10", "krypto": "15"},
    }
    for name, werte in presets.items():
        profil = RiskProfile(name=name)
        session.add(profil)
        session.flush()
        strategie = PortfolioStrategy(
            risk_profile_id=profil.id,
            max_einzelposition_pct=Decimal(werte["einzel"]),
            max_sektor_pct=Decimal("20"),
            cash_quote_ziel_pct=Decimal("5"),
            gesamt_exposure_cap_pct=Decimal("25"),
            aktiv=False,
        )
        session.add(strategie)
        session.flush()
        session.add(
            PortfolioClassLimit(
                portfolio_strategy_id=strategie.id,
                asset_class_id=KRYPTO_ID,
                max_klasse_pct=Decimal(werte["krypto"]),
            )
        )
    session.commit()
    return session


def test_waehle_risikoprofil_preset_activates_the_chosen_strategy() -> None:
    """@trace risikomanagement#AC3 — Aktivieren eines Presets setzt
    dessen `aktiv`-Flag."""
    session = _engine_mit_presets()

    strategie = waehle_risikoprofil_preset(session, risk_profile_name="konservativ")
    session.commit()

    assert strategie.aktiv is True
    assert strategie.max_einzelposition_pct == Decimal("2")


def test_waehle_risikoprofil_preset_switches_active_strategy_leaves_exactly_one_active() -> None:
    """@trace risikomanagement#AC3 — Umschalten zwischen zwei Presets lässt
    zu jedem Zeitpunkt genau EINE Depotstrategie aktiv (BR-117,
    App-seitige Durchsetzung, DB-seitig zusätzlich per partiellem
    UNIQUE-Index abgesichert — siehe Migration/Coder-Self-Test)."""
    session = _engine_mit_presets()

    konservativ = waehle_risikoprofil_preset(session, risk_profile_name="konservativ")
    session.commit()
    assert konservativ.aktiv is True

    offensiv = waehle_risikoprofil_preset(session, risk_profile_name="offensiv")
    session.commit()

    session.refresh(konservativ)
    assert konservativ.aktiv is False
    assert offensiv.aktiv is True


def test_waehle_risikoprofil_preset_respektiert_partiellen_unique_index() -> None:
    """@trace risikomanagement#AC3 — mehrfacher Preset-Wechsel gegen den
    TATSÄCHLICHEN partiellen Unique-Index (`WHERE aktiv`, BR-117) bleibt
    fehlerfrei: `waehle_risikoprofil_preset` flusht die Deaktivierung der
    bisherigen Zeile explizit VOR der Aktivierung der neuen, sonst ist die
    UPDATE-Emissionsreihenfolge in SQLAlchemy nicht determiniert und der
    Index wird nicht-deterministisch mit IntegrityError verletzt. Prüft
    zugleich, dass nach jedem Wechsel genau eine Zeile aktiv ist."""
    session = _engine_mit_presets(mit_partiellem_aktiv_index=True)

    for name in ("konservativ", "offensiv", "ausgewogen", "konservativ", "offensiv"):
        gewaehlt = waehle_risikoprofil_preset(session, risk_profile_name=name)
        session.commit()

        aktive = (
            session.execute(select(PortfolioStrategy).where(PortfolioStrategy.aktiv.is_(True)))
            .scalars()
            .all()
        )
        assert len(aktive) == 1
        assert aktive[0].id == gewaehlt.id


def test_waehle_risikoprofil_preset_rejects_unknown_profile_name() -> None:
    """@trace risikomanagement#AC3 — nur die 3 bekannten Presets sind
    wählbar."""
    session = _engine_mit_presets()
    with pytest.raises(RisikoprofilNichtGefundenError):
        waehle_risikoprofil_preset(session, risk_profile_name="unbekannt")


def test_passe_depotstrategie_an_updates_only_given_fields() -> None:
    """@trace risikomanagement#AC3 — Feinjustierung ändert nur die
    explizit übergebenen Felder, die übrigen bleiben unverändert."""
    session = _engine_mit_presets()
    strategie = waehle_risikoprofil_preset(session, risk_profile_name="ausgewogen")
    session.commit()
    ursprüngliche_cash_quote = strategie.cash_quote_ziel_pct

    aktualisiert = passe_depotstrategie_an(
        session, portfolio_strategy_id=strategie.id, max_einzelposition_pct=Decimal("7")
    )
    session.commit()

    assert aktualisiert.max_einzelposition_pct == Decimal("7")
    assert aktualisiert.cash_quote_ziel_pct == ursprüngliche_cash_quote


def test_passe_depotstrategie_an_rejects_unknown_id() -> None:
    """@trace risikomanagement#AC3 — eine nicht existierende
    Depotstrategie-ID wird abgelehnt, nicht stillschweigend ignoriert."""
    session = _engine_mit_presets()
    with pytest.raises(DepotstrategieNichtGefundenError):
        passe_depotstrategie_an(
            session, portfolio_strategy_id=uuid.uuid4(), max_einzelposition_pct=Decimal("7")
        )


def test_setze_klassen_limit_creates_new_limit_row() -> None:
    """@trace risikomanagement#AC1,AC3 — ein noch nicht konfiguriertes
    Klassen-Limit (hier: Aktien, id=1) kann per Feinjustierung ergänzt
    werden — über die per AC4 vorgeseedete Krypto-Zeile hinaus."""
    session = _engine_mit_presets()
    session.add(AssetClass(id=1, name="Aktien", prio_stufe="MVP", aktiv=True))
    session.commit()
    strategie = waehle_risikoprofil_preset(session, risk_profile_name="konservativ")
    session.commit()

    limit = setze_klassen_limit(
        session, portfolio_strategy_id=strategie.id, asset_class_id=1, max_klasse_pct=Decimal("30")
    )
    session.commit()

    assert limit.max_klasse_pct == Decimal("30")
    gefunden = session.get(PortfolioClassLimit, (strategie.id, 1))
    assert gefunden is not None
    assert gefunden.max_klasse_pct == Decimal("30")


def test_setze_klassen_limit_updates_existing_limit_row() -> None:
    """@trace risikomanagement#AC1,AC3 — ein bereits konfiguriertes
    Klassen-Limit (Krypto) wird per Feinjustierung überschrieben, nicht
    dupliziert."""
    session = _engine_mit_presets()
    strategie = waehle_risikoprofil_preset(session, risk_profile_name="konservativ")
    session.commit()
    assert strategie.max_einzelposition_pct == Decimal("2")

    setze_klassen_limit(
        session,
        portfolio_strategy_id=strategie.id,
        asset_class_id=KRYPTO_ID,
        max_klasse_pct=Decimal("8"),
    )
    session.commit()

    zeilen = (
        session.execute(
            select(PortfolioClassLimit).where(
                PortfolioClassLimit.portfolio_strategy_id == strategie.id,
                PortfolioClassLimit.asset_class_id == KRYPTO_ID,
            )
        )
        .scalars()
        .all()
    )
    assert len(zeilen) == 1
    assert zeilen[0].max_klasse_pct == Decimal("8")


def test_setze_klassen_limit_rejects_unknown_portfolio_strategy_id() -> None:
    """@trace risikomanagement#AC1,AC3 — eine nicht existierende
    Depotstrategie-ID wird abgelehnt."""
    session = _engine_mit_presets()
    with pytest.raises(DepotstrategieNichtGefundenError):
        setze_klassen_limit(
            session,
            portfolio_strategy_id=uuid.uuid4(),
            asset_class_id=KRYPTO_ID,
            max_klasse_pct=Decimal("10"),
        )


def test_lade_aktive_depotstrategie_returns_none_without_active_strategy() -> None:
    """@trace risikomanagement#AC11 — ohne aktive Depotstrategie liefert
    der einzige Lesepfad `None` (kein Grenzwert verfügbar), statt eine
    Strategie zu erraten."""
    session = _engine_mit_presets()
    assert lade_aktive_depotstrategie(session) is None


def test_lade_aktive_depotstrategie_returns_full_ac1_konfiguration() -> None:
    """@trace risikomanagement#AC1,AC4,AC11 — die aktive Depotstrategie
    liefert alle AC1-Grenzwerte (Einzelposition, Sektor, Cash-Quote,
    Klassen-Limits) unverändert aus dem Preset."""
    session = _engine_mit_presets()
    strategie = waehle_risikoprofil_preset(session, risk_profile_name="offensiv")
    session.commit()

    konfig = lade_aktive_depotstrategie(session)

    assert konfig is not None
    assert konfig.portfolio_strategy_id == strategie.id
    assert konfig.risk_profile_name == "offensiv"
    assert konfig.max_einzelposition_pct == Decimal("10")
    assert konfig.max_sektor_pct == Decimal("20")
    assert konfig.cash_quote_ziel_pct == Decimal("5")
    assert konfig.max_anlageklasse_pct == {KRYPTO_ID: Decimal("15")}


def test_lade_aktive_depotstrategie_reflects_switch_between_presets() -> None:
    """@trace risikomanagement#AC3,AC11 — nach einem Preset-Wechsel liefert
    der Lesepfad ausschliesslich die neu aktive Konfiguration."""
    session = _engine_mit_presets()
    waehle_risikoprofil_preset(session, risk_profile_name="konservativ")
    session.commit()
    waehle_risikoprofil_preset(session, risk_profile_name="ausgewogen")
    session.commit()

    konfig = lade_aktive_depotstrategie(session)

    assert konfig is not None
    assert konfig.risk_profile_name == "ausgewogen"
    assert konfig.max_einzelposition_pct == Decimal("5")
