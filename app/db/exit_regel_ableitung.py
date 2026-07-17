"""Exit-Regel-Ableitung: drei Kategorien, ATR-Stops, Default-Exit-Set &
ATR-Multiplikator (Story S-038, Spec `docs/specs/strategie-exit-regeln.md`).

Deckt:

- **AC6** — `leite_exit_regeln_ab()` liefert immer alle drei Exit-Regel-
  Kategorien: Thesis-Breakpoint (`thesis_invalidierung`, Pflicht — vom
  Aufrufer geliefert, hier nur validiert: nicht leer, sonst
  `ThesisInvalidierungFehltError`), Stop-Trigger (`stop_typ` +
  `stop_hinweis`, immer gesetzt) und Time-Box (`time_box`, optional, A2).
- **AC7** — der Default-Stop-Mechanismus ist ATR-basiert
  (`stop_typ == "atr_trailing"`), sooft die AC8-Tabelle keinen
  abweichenden Mechanismus vorschreibt (Ausnahme: `index_buy_and_hold`,
  wo die Spec-Tabelle selbst einen weiten Prozent-Stop vorsieht — siehe
  AC8-Präzisierung in der Spec). Kein fixer Prozent-Stop als blanket/
  generischer Default.
- **AC8** — `klassifiziere_exit_kategorie()` ordnet Strategie/Anlageklasse/
  Zeithorizont einer der 5 Default-Exit-Set-Kategorien zu (Priorität bei
  Überschneidung: Krypto > Daytrade/Swing > Strategie-Name > generischer
  AC7-Fallback, siehe AC8-Präzisierung); `lade_default_exit_set()` liest
  die zugehörige `exit_default_set`-Konfigurationszeile (Migration
  `655b7f43eff4`).
- **AC9** — `lade_atr_multiplikator()` liest den konfigurierten
  ATR-Multiplikator-Default je Volatilitätsklasse (`atr_multiplier_default`);
  `leite_exit_regeln_ab()` berechnet daraus bei `stop_typ == "atr_trailing"`
  den konkreten `stop_parameter = atr_wert * multiplikator`. Ist `atr_wert`
  `None` (Edge-Case „ATR nicht berechenbar (zu wenig Kurshistorie)"), bleibt
  `stop_parameter` `None` und `stop_unbestimmt` wird `True` — die Exit-Regel
  gilt dann als unvollständig (Edge-Cases & Fehlerverhalten der Spec).

Beide Konfigurationstabellen sind reine DB-Konfigurationsdaten (analog
`StrategyCluster.freigeschaltet`, S-037) — zur Laufzeit per `UPDATE`
änderbar, kein Code-/Migrations-Deploy nötig (NFR „zur Laufzeit
konfigurierbar" + „im Simulationsmodus kalibrierbar"). Alle Lookups sind
deterministisch (reine DB-Reads + Arithmetik) — kein LLM im Ableitungspfad
(NFR).

Was diese Story NICHT löst (Nicht-Ziele/Scope-Abgrenzung): die tatsächliche
Fixierung des Attribut-Bündels an einer Position (unveränderlich, `exit_rule`-
Zeile anlegen) ist S-040 (AC1/AC5/AC10/AC11) — dieses Modul liefert nur den
Vorschlag, den S-040 konsumiert oder durch eine manuelle Nutzer-/
Signalquellen-Eingabe überschreiben kann.
"""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

from sqlalchemy.orm import Session

from app.contracts.strategie_exit_regeln import ExitDefaultVorschlag, ExitKategorie, StopTyp
from app.db.models import AtrMultiplierDefault, ExitDefaultSet

# AC8-Präzisierung (Spec): Anlageklasse Kryptowährungen (data-model.md
# `asset_class`, id=7, Migration b2bd709be080) dominiert die Kategorisierung
# unabhängig von Strategie/Zeithorizont.
_KRYPTO_ASSET_CLASS_ID = 7

# AC8-Präzisierung (Spec): Zeithorizont-Stufen Daytrading (3)/Swing-Trading
# (4) — data-model.md `time_horizon`, Migration ddaf9dcc6216.
_DAYTRADE_SWING_HORIZONT_IDS = frozenset({3, 4})

# AC8-Präzisierung (Spec): "enges Zeitfenster" je Zeithorizont-Stufe —
# provisorischer, konfigurierbarer Default (Spec nennt nur "eng", keinen
# Zahlenwert).
_ENGES_ZEITFENSTER_JE_HORIZONT: dict[int, timedelta] = {
    3: timedelta(days=1),  # Daytrading
    4: timedelta(days=10),  # Swing-Trading (~2 Handelswochen)
}

#: AC9: die beiden gültigen Volatilitätsklassen (`atr_multiplier_default`-PK).
VOLATILITAETSKLASSEN = ("ruhig", "volatil")


class ThesisInvalidierungFehltError(ValueError):
    """AC6: der Thesis-Breakpoint (`thesis_invalidierung`) fehlt oder ist
    leer/nur Whitespace — diese Exit-Regel-Kategorie ist im Gegensatz zur
    Time-Box nie optional."""


class UnbekannteVolatilitaetsklasseError(ValueError):
    """AC9: `volatilitaetsklasse` ist keine der konfigurierten
    `atr_multiplier_default`-Zeilen."""


def klassifiziere_exit_kategorie(
    *, strategie_name: str, asset_class_id: int, zeithorizont_id: int
) -> ExitKategorie:
    """AC8: ordnet eine Strategie/Anlageklasse/Zeithorizont-Kombination
    einer der 5 Default-Exit-Set-Kategorien der Spec-Tabelle zu (oder dem
    generischen AC7-Fallback `"generisch"`).

    Priorität bei Überschneidung (AC8-Präzisierung in der Spec): Krypto
    (Anlageklasse) > Daytrade/Swing (Zeithorizont) > Strategie-Name
    (Value/Growth/Momentum/Index) > generischer Fallback — die
    volatilste/kurzfristigste Eigenschaft dominiert.
    """
    if asset_class_id == _KRYPTO_ASSET_CLASS_ID:
        return "krypto"
    if zeithorizont_id in _DAYTRADE_SWING_HORIZONT_IDS:
        return "daytrade_swing"
    if strategie_name == "Value":
        return "value_aktien"
    if strategie_name in ("Growth", "Momentum"):
        return "growth_momentum"
    if strategie_name == "Index":
        return "index_buy_and_hold"
    return "generisch"


def lade_default_exit_set(session: Session, *, kategorie: ExitKategorie) -> ExitDefaultSet | None:
    """AC8: lädt die `exit_default_set`-Konfigurationszeile für `kategorie`.

    `None` für den generischen Fallback (`kategorie == "generisch"`) — der
    hat bewusst keine eigene Tabellenzeile (AC7-Blanket-Default statt
    Tabellen-Override, siehe Modul-Docstring)."""
    if kategorie == "generisch":
        return None
    return session.get(ExitDefaultSet, kategorie)


def lade_atr_multiplikator(session: Session, *, volatilitaetsklasse: str) -> Decimal:
    """AC9: lädt den konfigurierten ATR-Multiplikator-Default für
    `volatilitaetsklasse` (`"ruhig"`/`"volatil"`).

    Raises:
        UnbekannteVolatilitaetsklasseError: `volatilitaetsklasse` ist keine
            gültige/konfigurierte Volatilitätsklasse.
    """
    if volatilitaetsklasse not in VOLATILITAETSKLASSEN:
        raise UnbekannteVolatilitaetsklasseError(
            f"Unbekannte Volatilitätsklasse {volatilitaetsklasse!r} "
            f"(erwartet {VOLATILITAETSKLASSEN})."
        )
    zeile = session.get(AtrMultiplierDefault, volatilitaetsklasse)
    if zeile is None:
        raise UnbekannteVolatilitaetsklasseError(
            f"Kein ATR-Multiplikator-Default für Volatilitätsklasse "
            f"{volatilitaetsklasse!r} konfiguriert (Konfigurationsdaten fehlen)."
        )
    return zeile.multiplikator


def _ist_leer(wert: str | None) -> bool:
    """Analog zu `app.contracts.depot._ist_leer` — `None` oder ein reiner
    Whitespace-String zählt als „fehlend"."""
    return wert is None or wert.strip() == ""


def leite_exit_regeln_ab(
    session: Session,
    *,
    strategie_name: str,
    asset_class_id: int,
    zeithorizont_id: int,
    volatilitaetsklasse: str,
    atr_wert: Decimal | None,
    thesis_invalidierung: str,
) -> ExitDefaultVorschlag:
    """Leitet den provisorischen Default-Exit-Regel-Vorschlag ab (AC6-AC9).

    Siehe Modul-Docstring für die AC-Zuordnung im Detail.

    Raises:
        ThesisInvalidierungFehltError: `thesis_invalidierung` ist leer/nur
            Whitespace (AC6: Thesis-Breakpoint ist nie optional).
        UnbekannteVolatilitaetsklasseError: siehe `lade_atr_multiplikator()`
            — wird nur ausgelöst, wenn tatsächlich ein ATR-Multiplikator
            benötigt wird (`stop_typ == "atr_trailing"` UND `atr_wert`
            gesetzt).
    """
    if _ist_leer(thesis_invalidierung):
        raise ThesisInvalidierungFehltError(
            "Thesis-Breakpoint (thesis_invalidierung) fehlt oder ist leer (AC6)."
        )

    kategorie = klassifiziere_exit_kategorie(
        strategie_name=strategie_name,
        asset_class_id=asset_class_id,
        zeithorizont_id=zeithorizont_id,
    )
    default_zeile = lade_default_exit_set(session, kategorie=kategorie)

    stop_typ: StopTyp
    stop_parameter_pct: Decimal | None
    if default_zeile is None:
        # AC7: generischer Fallback -- ATR-basiert (kein fixer Prozent-Stop
        # als blanket Default), kein Take-Profit-/Time-Box-Default.
        stop_typ = "atr_trailing"
        stop_hinweis = "ATR-Trailing-Stop (generischer AC7-Default, keine Kategorie-Tabellenzeile)"
        take_profit_hinweis: str | None = None
        time_box: timedelta | None = None
        stop_parameter_pct = None
    else:
        stop_typ = default_zeile.stop_typ  # type: ignore[assignment]
        stop_hinweis = default_zeile.stop_parameter_hinweis
        take_profit_hinweis = default_zeile.take_profit_hinweis
        time_box = default_zeile.time_box
        stop_parameter_pct = default_zeile.stop_parameter_pct

    if kategorie == "daytrade_swing":
        time_box = _ENGES_ZEITFENSTER_JE_HORIZONT.get(zeithorizont_id, time_box)

    stop_parameter: Decimal | None
    stop_unbestimmt = False
    if stop_typ == "atr_trailing":
        if atr_wert is None:
            # Edge-Case „ATR nicht berechenbar (zu wenig Kurshistorie)":
            # Stop-Parameter bleibt unbestimmt, Exit-Regel gilt als
            # unvollständig (Edge-Cases & Fehlerverhalten der Spec).
            stop_parameter = None
            stop_unbestimmt = True
        else:
            atr_multiplikator = lade_atr_multiplikator(
                session, volatilitaetsklasse=volatilitaetsklasse
            )
            stop_parameter = atr_wert * atr_multiplikator
    elif stop_typ == "fix_pct":
        stop_parameter = stop_parameter_pct
    else:
        # fundamental / technisch / keiner: kein numerischer Stop-Parameter
        # (qualitativer bzw. kursbezogener Mechanismus, siehe stop_hinweis).
        stop_parameter = None

    return ExitDefaultVorschlag(
        kategorie=kategorie,
        stop_typ=stop_typ,
        stop_hinweis=stop_hinweis,
        stop_parameter=stop_parameter,
        stop_unbestimmt=stop_unbestimmt,
        take_profit_hinweis=take_profit_hinweis,
        time_box=time_box,
        thesis_invalidierung=thesis_invalidierung,
    )
