"""Tests fuer die Exit-Regel-Ableitung (Story S-038).

Covers (strategie-exit-regeln): AC6, AC7, AC8, AC9

- AC6: `leite_exit_regeln_ab()` liefert immer drei Exit-Regel-Kategorien
  (Thesis-Breakpoint, Stop-Trigger, Time-Box); Thesis-Breakpoint und
  Stop-Trigger sind nie leer (Stop-Typ + Stop-Hinweis immer gesetzt), die
  Time-Box darf `None` sein (deckt A2).
- AC7: der Stop-Mechanismus ist per Default ATR-basiert (`atr_trailing`),
  kein fixer Prozent-Stop als blanket/generischer Default — die einzige
  `fix_pct`-Ausnahme (`index_buy_and_hold`) ist eine explizite
  AC8-Tabellenzeile, kein blanket Verhalten.
- AC8: `klassifiziere_exit_kategorie()` ordnet Strategie/Anlageklasse/
  Zeithorizont den 5 Spec-Tabellenkategorien (oder dem generischen
  Fallback) zu; `leite_exit_regeln_ab()`/`lade_default_exit_set()` liefern
  je Kategorie die konfigurierten Startwerte aus `exit_default_set`.
- AC9: `lade_atr_multiplikator()` liest den konfigurierten
  ATR-Multiplikator je Volatilitätsklasse (`atr_multiplier_default`);
  `leite_exit_regeln_ab()` berechnet daraus den konkreten Stop-Parameter
  (`atr_wert * multiplikator`) bzw. kennzeichnet ihn als unbestimmt, wenn
  `atr_wert` fehlt (Edge-Case „ATR nicht berechenbar").

Seed-Konstanten werden direkt aus der Migrationsdatei importiert (statt
dupliziert), analog `tests/db/test_strategie_katalog_migration.py`.
"""

from __future__ import annotations

import importlib.util
from datetime import timedelta
from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.db.base import Base
from app.db.exit_regel_ableitung import (
    ThesisInvalidierungFehltError,
    UnbekannteVolatilitaetsklasseError,
    klassifiziere_exit_kategorie,
    lade_atr_multiplikator,
    lade_default_exit_set,
    leite_exit_regeln_ab,
)
from app.db.models import AtrMultiplierDefault, ExitDefaultSet

MIGRATION_PATH = (
    Path(__file__).parents[2]
    / "app"
    / "db"
    / "migrations"
    / "versions"
    / "655b7f43eff4_create_exit_default_set_and_atr_.py"
)


def _load_migration_module():
    spec = importlib.util.spec_from_file_location("exit_regel_ableitung_migration", MIGRATION_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


_MIGRATION = _load_migration_module()
EXIT_DEFAULT_SET_SEED = _MIGRATION.EXIT_DEFAULT_SET_SEED
ATR_MULTIPLIER_DEFAULT_SEED = _MIGRATION.ATR_MULTIPLIER_DEFAULT_SEED


def _als_decimal(wert: object) -> Decimal | None:
    return None if wert is None else Decimal(str(wert))


@pytest.fixture()
def session() -> Session:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as db_session:
        for row in EXIT_DEFAULT_SET_SEED:
            db_session.add(
                ExitDefaultSet(
                    kategorie=row["kategorie"],
                    stop_typ=row["stop_typ"],
                    stop_parameter_hinweis=row["stop_parameter_hinweis"],
                    stop_parameter_pct=_als_decimal(row["stop_parameter_pct"]),
                    take_profit_hinweis=row["take_profit_hinweis"],
                    time_box=row["time_box"],
                )
            )
        for row in ATR_MULTIPLIER_DEFAULT_SEED:
            db_session.add(
                AtrMultiplierDefault(
                    volatilitaetsklasse=row["volatilitaetsklasse"],
                    multiplikator=_als_decimal(row["multiplikator"]),
                    multiplikator_min=_als_decimal(row["multiplikator_min"]),
                    multiplikator_max=_als_decimal(row["multiplikator_max"]),
                )
            )
        db_session.commit()
        yield db_session


# --- AC8: Klassifikation --------------------------------------------------


def test_krypto_dominiert_unabhaengig_von_strategie_und_zeithorizont() -> None:
    """@trace strategie-exit-regeln#AC8 — die Anlageklasse Krypto (id=7)
    dominiert die Kategorisierung unabhaengig von Strategie/Zeithorizont
    (AC8-Praezisierung: hoechste Prioritaet)."""
    kategorie = klassifiziere_exit_kategorie(
        strategie_name="Value", asset_class_id=7, zeithorizont_id=3
    )
    assert kategorie == "krypto"


@pytest.mark.parametrize("zeithorizont_id", [3, 4])
def test_daytrade_swing_horizont_dominiert_ueber_strategie_name(zeithorizont_id: int) -> None:
    """@trace strategie-exit-regeln#AC8 — Zeithorizont Daytrading (3)/
    Swing-Trading (4) klassifiziert als daytrade_swing, unabhaengig vom
    Strategie-Namen (AC8-Praezisierung: zweithoechste Prioritaet)."""
    kategorie = klassifiziere_exit_kategorie(
        strategie_name="Index", asset_class_id=1, zeithorizont_id=zeithorizont_id
    )
    assert kategorie == "daytrade_swing"


def test_value_strategie_klassifiziert_als_value_aktien() -> None:
    """@trace strategie-exit-regeln#AC8 — Strategie "Value" -> Kategorie
    value_aktien."""
    kategorie = klassifiziere_exit_kategorie(
        strategie_name="Value", asset_class_id=1, zeithorizont_id=6
    )
    assert kategorie == "value_aktien"


@pytest.mark.parametrize("strategie_name", ["Growth", "Momentum"])
def test_growth_und_momentum_klassifizieren_als_growth_momentum(strategie_name: str) -> None:
    """@trace strategie-exit-regeln#AC8 — Strategie "Growth"/"Momentum" ->
    Kategorie growth_momentum."""
    kategorie = klassifiziere_exit_kategorie(
        strategie_name=strategie_name, asset_class_id=1, zeithorizont_id=6
    )
    assert kategorie == "growth_momentum"


def test_index_strategie_klassifiziert_als_index_buy_and_hold() -> None:
    """@trace strategie-exit-regeln#AC8 — Strategie "Index" -> Kategorie
    index_buy_and_hold."""
    kategorie = klassifiziere_exit_kategorie(
        strategie_name="Index", asset_class_id=2, zeithorizont_id=8
    )
    assert kategorie == "index_buy_and_hold"


@pytest.mark.parametrize("strategie_name", ["DCA", "Dividende", "Factor/Smart Beta"])
def test_mvp_strategien_ohne_eigene_tabellenzeile_klassifizieren_als_generisch(
    strategie_name: str,
) -> None:
    """@trace strategie-exit-regeln#AC8 — weitere MVP-Strategien ohne
    eigene AC8-Tabellenzeile (DCA, Dividende, Factor/Smart Beta) fallen auf
    den generischen AC7-Fallback zurueck (AC8-Praezisierung)."""
    kategorie = klassifiziere_exit_kategorie(
        strategie_name=strategie_name, asset_class_id=1, zeithorizont_id=6
    )
    assert kategorie == "generisch"


# --- AC8: Konfigurationszeile laden ---------------------------------------


@pytest.mark.parametrize(
    "kategorie",
    ["value_aktien", "growth_momentum", "index_buy_and_hold", "krypto", "daytrade_swing"],
)
def test_lade_default_exit_set_liefert_konfigurierte_zeile_je_kategorie(
    session: Session, kategorie: str
) -> None:
    """@trace strategie-exit-regeln#AC8 — jede der 5 Spec-Tabellenkategorien
    hat eine konfigurierte `exit_default_set`-Zeile."""
    zeile = lade_default_exit_set(session, kategorie=kategorie)  # type: ignore[arg-type]
    assert zeile is not None
    assert zeile.stop_typ
    assert zeile.stop_parameter_hinweis.strip()


def test_lade_default_exit_set_liefert_none_fuer_generischen_fallback(session: Session) -> None:
    """@trace strategie-exit-regeln#AC8 — der generische Fallback hat
    bewusst KEINE eigene `exit_default_set`-Zeile (AC7-Blanket-Default)."""
    assert lade_default_exit_set(session, kategorie="generisch") is None


# --- AC9: ATR-Multiplikator ------------------------------------------------


def test_lade_atr_multiplikator_liefert_konfigurierten_wert_je_volatilitaetsklasse(
    session: Session,
) -> None:
    """@trace strategie-exit-regeln#AC9 — ATR-Multiplikator ist als
    provisorischer, konfigurierbarer Default je Volatilitaetsklasse
    hinterlegt (Richtwert ruhig 2-2.5x, volatil 3-4x)."""
    ruhig = lade_atr_multiplikator(session, volatilitaetsklasse="ruhig")
    volatil = lade_atr_multiplikator(session, volatilitaetsklasse="volatil")

    assert Decimal("2.0") <= ruhig <= Decimal("2.5")
    assert Decimal("3.0") <= volatil <= Decimal("4.0")
    assert ruhig < volatil


def test_lade_atr_multiplikator_lehnt_unbekannte_volatilitaetsklasse_ab(session: Session) -> None:
    """@trace strategie-exit-regeln#AC9 — nur "ruhig"/"volatil" sind
    gueltige Volatilitaetsklassen."""
    with pytest.raises(UnbekannteVolatilitaetsklasseError):
        lade_atr_multiplikator(session, volatilitaetsklasse="extrem")


# --- AC6/AC7/AC8/AC9: volle Ableitung --------------------------------------


def test_value_aktien_liefert_fundamentalen_stop_ohne_atr_und_mit_time_box(
    session: Session,
) -> None:
    """@trace strategie-exit-regeln#AC6,AC7,AC8 — Value (Aktien): kein
    ATR-/Prozent-Stop-Parameter (fundamentaler Stop, "These bricht"),
    Time-Box gesetzt (~3 Jahre) — deckt AC6 (Stop-Trigger nie leer, auch
    ohne numerischen Parameter) und AC8 (Value-Tabellenzeile)."""
    vorschlag = leite_exit_regeln_ab(
        session,
        strategie_name="Value",
        asset_class_id=1,
        zeithorizont_id=6,
        volatilitaetsklasse="ruhig",
        atr_wert=None,
        thesis_invalidierung="Fundamentaldaten verschlechtern sich unter Zielwert",
    )

    assert vorschlag.kategorie == "value_aktien"
    assert vorschlag.stop_typ == "fundamental"
    assert vorschlag.stop_hinweis.strip()
    assert vorschlag.stop_parameter is None
    assert vorschlag.stop_unbestimmt is False
    assert vorschlag.time_box == timedelta(days=3 * 365)
    assert vorschlag.thesis_invalidierung == "Fundamentaldaten verschlechtern sich unter Zielwert"


def test_growth_momentum_atr_stop_wird_aus_atr_wert_und_multiplikator_berechnet(
    session: Session,
) -> None:
    """@trace strategie-exit-regeln#AC7,AC8,AC9 — Growth/Momentum nutzt
    ATR-Trailing-Stop; der konkrete Stop-Parameter ist `atr_wert *
    atr_multiplikator` (AC9)."""
    atr_wert = Decimal("2.00")
    multiplikator = lade_atr_multiplikator(session, volatilitaetsklasse="volatil")

    vorschlag = leite_exit_regeln_ab(
        session,
        strategie_name="Growth",
        asset_class_id=1,
        zeithorizont_id=6,
        volatilitaetsklasse="volatil",
        atr_wert=atr_wert,
        thesis_invalidierung="Umsatzwachstum faellt unter 15% YoY",
    )

    assert vorschlag.kategorie == "growth_momentum"
    assert vorschlag.stop_typ == "atr_trailing"
    assert vorschlag.stop_parameter == atr_wert * multiplikator
    assert vorschlag.stop_unbestimmt is False
    assert vorschlag.time_box is None
    assert vorschlag.take_profit_hinweis is not None


def test_krypto_klassifikation_dominiert_und_liefert_atr_trailing(session: Session) -> None:
    """@trace strategie-exit-regeln#AC8 — eine Krypto-Position (Anlageklasse
    7) mit Value-Strategie wird trotzdem als "krypto" behandelt (AC8-
    Praezisierung: Klassen-Prioritaet)."""
    vorschlag = leite_exit_regeln_ab(
        session,
        strategie_name="Value",
        asset_class_id=7,
        zeithorizont_id=6,
        volatilitaetsklasse="volatil",
        atr_wert=Decimal("500"),
        thesis_invalidierung="Netzwerk-Adoption stagniert",
    )

    assert vorschlag.kategorie == "krypto"
    assert vorschlag.stop_typ == "atr_trailing"
    assert vorschlag.stop_parameter is not None


def test_daytrade_swing_hat_technischen_stop_und_enges_zeitfenster(session: Session) -> None:
    """@trace strategie-exit-regeln#AC6,AC8 — Daytrade/Swing: technischer
    Stop (kein ATR-/Prozent-Parameter), Time-Box gesetzt ("enges
    Zeitfenster", AC8-Praezisierung: 1 Tag bei Daytrading)."""
    vorschlag = leite_exit_regeln_ab(
        session,
        strategie_name="Momentum",
        asset_class_id=1,
        zeithorizont_id=3,
        volatilitaetsklasse="volatil",
        atr_wert=None,
        thesis_invalidierung="Support-Level bricht intraday",
    )

    assert vorschlag.kategorie == "daytrade_swing"
    assert vorschlag.stop_typ == "technisch"
    assert vorschlag.stop_hinweis.strip()
    assert vorschlag.stop_parameter is None
    assert vorschlag.stop_unbestimmt is False
    assert vorschlag.time_box == timedelta(days=1)


def test_index_buy_and_hold_nutzt_fix_pct_stop_als_explizite_ac8_ausnahme(
    session: Session,
) -> None:
    """@trace strategie-exit-regeln#AC7,AC8 — Index/Buy-and-Hold ist die
    einzige Kategorie mit `stop_typ == "fix_pct"` (Spannen-Mittelpunkt
    27.5%, AC8-Praezisierung) — eine explizite Tabellenzeile, kein
    blanket/generischer Fixed-Pct-Default (AC7)."""
    vorschlag = leite_exit_regeln_ab(
        session,
        strategie_name="Index",
        asset_class_id=2,
        zeithorizont_id=8,
        volatilitaetsklasse="ruhig",
        atr_wert=None,
        thesis_invalidierung="Index verlaesst strukturell den Zielsektor",
    )

    assert vorschlag.kategorie == "index_buy_and_hold"
    assert vorschlag.stop_typ == "fix_pct"
    assert vorschlag.stop_parameter == Decimal("27.5")
    assert vorschlag.time_box is None


def test_generischer_fallback_nutzt_atr_trailing_ohne_take_profit_oder_time_box(
    session: Session,
) -> None:
    """@trace strategie-exit-regeln#AC7,AC8 — eine Strategie ohne eigene
    AC8-Tabellenzeile (z.B. DCA) bekommt den generischen ATR-basierten
    Default (AC7: kein fixer Prozent-Stop als blanket Default)."""
    vorschlag = leite_exit_regeln_ab(
        session,
        strategie_name="DCA",
        asset_class_id=1,
        zeithorizont_id=7,
        volatilitaetsklasse="ruhig",
        atr_wert=Decimal("1.5"),
        thesis_invalidierung="Sparplan-These entfaellt bei Dividendenkuerzung",
    )

    assert vorschlag.kategorie == "generisch"
    assert vorschlag.stop_typ == "atr_trailing"
    assert vorschlag.stop_parameter is not None
    assert vorschlag.take_profit_hinweis is None
    assert vorschlag.time_box is None


def test_atr_nicht_berechenbar_markiert_stop_parameter_als_unbestimmt(session: Session) -> None:
    """@trace strategie-exit-regeln#AC7,AC9 — Edge-Case "ATR nicht
    berechenbar (zu wenig Kurshistorie)": `stop_parameter` bleibt `None`,
    `stop_unbestimmt` wird `True` (Exit-Regel gilt als unvollstaendig)."""
    vorschlag = leite_exit_regeln_ab(
        session,
        strategie_name="Growth",
        asset_class_id=1,
        zeithorizont_id=6,
        volatilitaetsklasse="ruhig",
        atr_wert=None,
        thesis_invalidierung="Marge bricht unter 20%",
    )

    assert vorschlag.stop_typ == "atr_trailing"
    assert vorschlag.stop_parameter is None
    assert vorschlag.stop_unbestimmt is True


def test_thesis_invalidierung_leer_wird_abgelehnt(session: Session) -> None:
    """@trace strategie-exit-regeln#AC6 — der Thesis-Breakpoint darf nicht
    leer sein (auch kein reiner Whitespace-String)."""
    with pytest.raises(ThesisInvalidierungFehltError):
        leite_exit_regeln_ab(
            session,
            strategie_name="Index",
            asset_class_id=2,
            zeithorizont_id=8,
            volatilitaetsklasse="ruhig",
            atr_wert=None,
            thesis_invalidierung="   ",
        )


def test_thesis_invalidierung_none_wird_abgelehnt(session: Session) -> None:
    """@trace strategie-exit-regeln#AC6 — `None` zaehlt ebenfalls als
    fehlender Thesis-Breakpoint."""
    with pytest.raises(ThesisInvalidierungFehltError):
        leite_exit_regeln_ab(
            session,
            strategie_name="Index",
            asset_class_id=2,
            zeithorizont_id=8,
            volatilitaetsklasse="ruhig",
            atr_wert=None,
            thesis_invalidierung=None,  # type: ignore[arg-type]
        )


@pytest.mark.parametrize(
    "strategie_name,asset_class_id,zeithorizont_id,volatilitaetsklasse,atr_wert",
    [
        ("Value", 1, 6, "ruhig", None),
        ("Growth", 1, 6, "volatil", Decimal("2")),
        ("Index", 2, 8, "ruhig", None),
        ("Value", 7, 6, "volatil", Decimal("500")),
        ("Momentum", 1, 3, "volatil", None),
        ("DCA", 1, 7, "ruhig", Decimal("1.5")),
    ],
)
def test_stop_trigger_kategorie_ist_ueber_alle_faelle_nie_leer(
    session: Session,
    strategie_name: str,
    asset_class_id: int,
    zeithorizont_id: int,
    volatilitaetsklasse: str,
    atr_wert: Decimal | None,
) -> None:
    """@trace strategie-exit-regeln#AC6 — ueber alle 5 Kategorien + den
    generischen Fallback ist der Stop-Trigger (`stop_typ`/`stop_hinweis`)
    immer gesetzt — nur die Time-Box darf leer sein (deckt A2)."""
    vorschlag = leite_exit_regeln_ab(
        session,
        strategie_name=strategie_name,
        asset_class_id=asset_class_id,
        zeithorizont_id=zeithorizont_id,
        volatilitaetsklasse=volatilitaetsklasse,
        atr_wert=atr_wert,
        thesis_invalidierung="Testthese",
    )

    assert vorschlag.stop_typ
    assert vorschlag.stop_hinweis.strip()
    assert vorschlag.thesis_invalidierung.strip()
