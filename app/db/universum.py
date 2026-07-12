"""Survivorship-bias-freies historisches Titel-Universum (Story S-051).

Deckt `docs/specs/datenqualitaet.md` AC5:

- **AC5 (Survivorship-Bias-Vermeidung):** `historisches_universum()`
  beantwortet "welche Titel existierten zum Zeitpunkt X" ausschliesslich
  ueber tatsaechlich vorhandene `market_data_silver`-Beobachtungen mit
  `observed_at <= stand_zeitpunkt` — ein Symbol bleibt im Ergebnis, sobald es
  mindestens eine Beobachtung bis `stand_zeitpunkt` hat, UNABHAENGIG davon,
  ob es danach weiterhin beobachtet wird. Es gibt in dieser Funktion
  strukturell KEINEN Filter auf einen "aktuell aktiv/gelistet"-Status (kein
  Join auf eine Stammdaten-/Instrument-Tabelle mit `aktiv`-Flag) — genau das
  waere der klassische Survivorship-Bias-Fehler (spaeter verschwundene Titel
  aus der historischen Auswertung ausschliessen).

  **Edge-Case "Delisting eines gehaltenen Titels":** ein Symbol, das nach
  `stand_zeitpunkt` delisted wird (keine weiteren Bronze-/Silver-
  Beobachtungen mehr erhaelt), verschwindet NICHT aus einer Abfrage mit
  einem `stand_zeitpunkt` VOR oder WAEHREND seines aktiven Zeitraums —
  Beobachtungen werden nie geloescht (Bronze: BR-121 append-only; Silver:
  nur bei Corporate-Actions-Neuableitung ersetzt, nicht entfernt), die
  Symbol-Zugehoerigkeit einer bereits eingetroffenen Beobachtung aendert sich
  daher nie rueckwirkend.

- **Warum keine neue Instrument-/Delisting-Tabelle:** die `instrument`-
  Tabelle existiert in dieser Codebasis noch nicht (siehe
  data-model.md-Praezisierung + Coder-Handoff S-024/S-051) — ein explizites
  "Delisting-Datum" je Titel zu modellieren waere eine Schema-/
  Architektur-Entscheidung ausserhalb des Scopes dieser Story (potenzielle
  Folge-Story, sobald `instrument` existiert). AC5 verlangt nur, dass
  delistete Titel NICHT aus der historischen Auswertung verschwinden — das
  ist bereits durch die reine Beobachtungs-Historie (Silver, per AC1/BR-121
  append-only in Bronze fundiert) strukturell erfuellt, ohne dass eine
  weitere Tabelle noetig ist.

- **Warum Silver statt Bronze als Quelle:** die Spec ordnet
  "Survivorship-bereinigte Titel-Universen" im Main-Success-Scenario
  ausdruecklich der Silver-Schicht zu (Schritt 4). Silver enthaelt nur
  Beobachtungen valider Bronze-Kandidaten (AC7/AC8-Gate via
  `app.db.silver.record_silver_observation`) — ein Universum aus Silver ist
  damit konsistent mit "nur valide Datenpunkte" (AC7), waehrend Bronze auch
  inhaltlich fehlerhafte/verworfene Kandidaten enthalten wuerde.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import MarketDataSilver


def historisches_universum(
    session: Session,
    *,
    stand_zeitpunkt: datetime,
    data_source_id: uuid.UUID | None = None,
) -> list[str]:
    """AC5: liefert alle Symbole, fuer die zum `stand_zeitpunkt` bereits
    mindestens eine Silver-Beobachtung vorlag (`observed_at <=
    stand_zeitpunkt`) — survivorship-bias-frei, alphabetisch sortiert.

    `data_source_id` schraenkt optional auf eine einzelne Quelle ein (sonst
    ueber alle Quellen hinweg). Symbole ohne beobachteten Wert (`symbol IS
    NULL`) sind kein Titel-Universum-Mitglied und werden ausgeschlossen.
    """
    filter_bedingungen = [
        MarketDataSilver.observed_at <= stand_zeitpunkt,
        MarketDataSilver.symbol.is_not(None),
    ]
    if data_source_id is not None:
        filter_bedingungen.append(MarketDataSilver.data_source_id == data_source_id)

    symbole = (
        session.execute(select(MarketDataSilver.symbol).where(*filter_bedingungen).distinct())
        .scalars()
        .all()
    )
    return sorted(symbole)


__all__ = ["historisches_universum"]
