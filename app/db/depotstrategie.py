"""Depotstrategie-Regelwerk: Preset-Auswahl, Feinjustierung, aktive
Konfiguration (Story S-043).

Deckt `docs/specs/risikomanagement.md`:

- **AC1 (Grenzwert-Regelwerk):** das Schema selbst (`app.db.models.
  RiskProfile`/`PortfolioStrategy`/`PortfolioClassLimit`) trägt mindestens
  max. Gewicht je Branche/Sektor (GICS, `max_sektor_pct` — EIN flacher
  Wert je Depotstrategie), max. Gewicht je Anlageklasse
  (`PortfolioClassLimit.max_klasse_pct`), max. Einzelposition
  (`max_einzelposition_pct`) und Cash-Quote (`cash_quote_ziel_pct`).

- **AC3 (3 Presets, Auswahl + Feinjustierung):** `waehle_risikoprofil_
  preset()` aktiviert eine der drei per Migration geseedeten
  `PortfolioStrategy`-Zeilen (konservativ/ausgewogen/offensiv) — genau eine
  ist zu jedem Zeitpunkt `aktiv=True` (BR-117, App-seitige Durchsetzung
  hier, DB-seitig zusätzlich per partiellem UNIQUE-Index, siehe Migration).
  `passe_depotstrategie_an()` + `setze_klassen_limit()` erlauben die
  anschliessende Feinjustierung einzelner Werte (In-Place-UPDATE, keine
  Versionierung — siehe `PortfolioStrategy`-Docstring).

- **AC11 (Gate bezieht Limits ausschliesslich aus der Depotstrategie):**
  `lade_aktive_depotstrategie()` ist der EINZIGE Lesepfad, der die
  vollständige, aktuell aktive Konfiguration als
  `DepotstrategieKonfiguration`-Vertrag zusammenstellt — ein künftiges
  Risikomanagement-Gate (AC5-AC10, ausserhalb dieser Story) konsumiert
  ausschliesslich diesen Vertrag und definiert keine eigenen Grenzwerte.

Das Risikomanagement-Gate selbst (AC5-AC10: Klumpenrisiko-/Korrelations-
/Drawdown-Prüfung, Drei-Wege-Entscheid) ist NICHT Teil dieser Story — dieses
Modul liefert ausschliesslich das konfigurierbare Regelwerk, das ein
künftiges Gate konsumiert (AC11).
"""

from __future__ import annotations

import uuid
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.contracts.risikomanagement import DepotstrategieKonfiguration
from app.db.models import RISK_PROFILE_NAMES, PortfolioClassLimit, PortfolioStrategy, RiskProfile


class RisikoprofilNichtGefundenError(LookupError):
    """`risk_profile_name` ist keiner der drei bekannten Presets
    (`RISK_PROFILE_NAMES`) bzw. es existiert keine passende
    `PortfolioStrategy`-Zeile dazu."""


class DepotstrategieNichtGefundenError(LookupError):
    """`portfolio_strategy_id` referenziert keine bekannte Depotstrategie."""


def _deaktiviere_aktive_strategie(session: Session) -> None:
    """Setzt eine ggf. aktive `PortfolioStrategy`-Zeile auf `aktiv=False` —
    Voraussetzung für BR-117 (genau eine aktive Depotstrategie), bevor eine
    andere Zeile aktiviert wird (Muster von `app.db.config_versions.
    _markiere_bisherige_version_als_veraltet` übernommen)."""
    bisherige = (
        session.execute(select(PortfolioStrategy).where(PortfolioStrategy.aktiv.is_(True)))
        .scalars()
        .all()
    )
    for strategie in bisherige:
        strategie.aktiv = False


def waehle_risikoprofil_preset(session: Session, *, risk_profile_name: str) -> PortfolioStrategy:
    """AC3: aktiviert das `PortfolioStrategy`-Preset zu `risk_profile_name`
    (konservativ/ausgewogen/offensiv) — deaktiviert zuerst eine ggf. bereits
    aktive Depotstrategie (BR-117: genau eine aktive Zeile).

    Raises:
        RisikoprofilNichtGefundenError: `risk_profile_name` ist keines der
            drei bekannten Presets, oder es existiert (noch) keine
            `PortfolioStrategy`-Zeile für dieses Profil.
    """
    if risk_profile_name not in RISK_PROFILE_NAMES:
        raise RisikoprofilNichtGefundenError(
            f"Unbekanntes Risikoprofil {risk_profile_name!r} (erwartet eines von "
            f"{RISK_PROFILE_NAMES})."
        )

    zeile = session.execute(
        select(PortfolioStrategy)
        .join(RiskProfile, PortfolioStrategy.risk_profile_id == RiskProfile.id)
        .where(RiskProfile.name == risk_profile_name)
    ).scalar_one_or_none()
    if zeile is None:
        raise RisikoprofilNichtGefundenError(
            f"Keine Depotstrategie-Preset-Zeile für Risikoprofil {risk_profile_name!r} "
            "konfiguriert."
        )

    _deaktiviere_aktive_strategie(session)
    zeile.aktiv = True
    return zeile


def passe_depotstrategie_an(
    session: Session,
    *,
    portfolio_strategy_id: uuid.UUID,
    max_einzelposition_pct: Decimal | None = None,
    max_sektor_pct: Decimal | None = None,
    cash_quote_ziel_pct: Decimal | None = None,
    gesamt_exposure_cap_pct: Decimal | None = None,
) -> PortfolioStrategy:
    """AC3 "einzelne Werte feinjustieren": aktualisiert nur die explizit
    übergebenen (nicht-`None`) Felder der Depotstrategie-Zeile — In-Place,
    keine Versionierung. Wertebereiche (0-100 %) werden von den
    DB-CHECK-Constraints durchgesetzt (siehe Migration).

    Raises:
        DepotstrategieNichtGefundenError: `portfolio_strategy_id` existiert
            nicht.
    """
    zeile = session.get(PortfolioStrategy, portfolio_strategy_id)
    if zeile is None:
        raise DepotstrategieNichtGefundenError(
            f"Depotstrategie {portfolio_strategy_id!r} existiert nicht."
        )

    if max_einzelposition_pct is not None:
        zeile.max_einzelposition_pct = max_einzelposition_pct
    if max_sektor_pct is not None:
        zeile.max_sektor_pct = max_sektor_pct
    if cash_quote_ziel_pct is not None:
        zeile.cash_quote_ziel_pct = cash_quote_ziel_pct
    if gesamt_exposure_cap_pct is not None:
        zeile.gesamt_exposure_cap_pct = gesamt_exposure_cap_pct
    return zeile


def setze_klassen_limit(
    session: Session,
    *,
    portfolio_strategy_id: uuid.UUID,
    asset_class_id: int,
    max_klasse_pct: Decimal,
) -> PortfolioClassLimit:
    """AC1/AC3: legt das Klassen-Limit für `asset_class_id` einer
    Depotstrategie an oder aktualisiert es (Upsert) — Feinjustierung des
    AC1-Grenzwert-Regelwerks "max. Gewicht je Anlageklasse" über die per
    AC4 vorgeseedete Krypto-Zeile hinaus.

    Raises:
        DepotstrategieNichtGefundenError: `portfolio_strategy_id` existiert
            nicht.
    """
    if session.get(PortfolioStrategy, portfolio_strategy_id) is None:
        raise DepotstrategieNichtGefundenError(
            f"Depotstrategie {portfolio_strategy_id!r} existiert nicht."
        )

    zeile = session.get(PortfolioClassLimit, (portfolio_strategy_id, asset_class_id))
    if zeile is None:
        zeile = PortfolioClassLimit(
            portfolio_strategy_id=portfolio_strategy_id,
            asset_class_id=asset_class_id,
            max_klasse_pct=max_klasse_pct,
        )
        session.add(zeile)
    else:
        zeile.max_klasse_pct = max_klasse_pct
    return zeile


def lade_aktive_depotstrategie(session: Session) -> DepotstrategieKonfiguration | None:
    """AC11: lädt die aktuell aktive Depotstrategie (`aktiv=True`) samt
    ihrer Klassen-Limits als vollständigen `DepotstrategieKonfiguration`-
    Vertrag — der EINZIGE Lesepfad, den ein künftiges Risikomanagement-Gate
    konsumieren darf (AC11: "definiert keine eigenen Grenzwerte").

    Returns:
        `None`, wenn aktuell keine Depotstrategie aktiv ist (z.B. vor der
        ersten Preset-Wahl, AC3) — ein Gate-Konsument muss diesen Fall
        analog E1 der Spec behandeln (kein Grenzwert verfügbar -> keine
        Freigabe), das ist jedoch Sache des (künftigen) Gate-Moduls, nicht
        dieser Story.
    """
    strategie = session.execute(
        select(PortfolioStrategy).where(PortfolioStrategy.aktiv.is_(True))
    ).scalar_one_or_none()
    if strategie is None:
        return None

    risk_profile = session.get(RiskProfile, strategie.risk_profile_id)
    assert risk_profile is not None  # FK-Garantie: risk_profile_id ist NOT NULL + FK

    klassen_limits = (
        session.execute(
            select(PortfolioClassLimit).where(
                PortfolioClassLimit.portfolio_strategy_id == strategie.id
            )
        )
        .scalars()
        .all()
    )

    return DepotstrategieKonfiguration(
        portfolio_strategy_id=strategie.id,
        risk_profile_name=risk_profile.name,
        max_einzelposition_pct=strategie.max_einzelposition_pct,
        max_sektor_pct=strategie.max_sektor_pct,
        cash_quote_ziel_pct=strategie.cash_quote_ziel_pct,
        gesamt_exposure_cap_pct=strategie.gesamt_exposure_cap_pct,
        max_anlageklasse_pct={
            limit.asset_class_id: limit.max_klasse_pct for limit in klassen_limits
        },
    )


__all__ = [
    "RisikoprofilNichtGefundenError",
    "DepotstrategieNichtGefundenError",
    "waehle_risikoprofil_preset",
    "passe_depotstrategie_an",
    "setze_klassen_limit",
    "lade_aktive_depotstrategie",
]
