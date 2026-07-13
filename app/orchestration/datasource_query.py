"""Geteilte Datenquellen-Abfrage (Modul 2, architecture.md §3/P4) — Story S-021.

Deckt `docs/specs/dateneingang.md`:

- **AC7 ("eine Schnittstelle, drei Konsumenten"):** `hole_signal_buendel()`
  ist die EINZIGE Funktion, über die Suchkriteria (Konsumenten-Kontext
  `"neu"`), Depot-Suchkriterien (`"bestehend"`) und Research (`"research"`)
  Signal-Bündel beziehen. `konsumenten_kontext` fliesst bewusst NICHT in die
  Auswahl-/Aggregationslogik ein — alle drei Konsumenten durchlaufen exakt
  denselben Code-Pfad (keine parallele Zweit-Implementierung je Konsument,
  architecture.md P4 "Genau ein Modul `datasource_query`").

- **AC8 (Registry-basierte Auswahl + Aggregation):** je Titel-Anfrage wählt
  `_passende_quellen()` anhand der Anlageklasse aus der Quellen-Registry
  (`app.db.models.DataSourceAssetClass`, AC5/AC6, S-006) die zugeordneten,
  aktiven Quellen; für jede passende Quelle wird die bereits validierte,
  angereicherte Gold-Historie (`app.db.models.MarketDataGold`, AC4 aus
  `docs/specs/datenqualitaet.md`) für den angefragten Titel gelesen — dieses
  Modul betreibt selbst KEINE Socket-/Adapter-Anbindung und schreibt keine
  neuen Bronze/Silver/Gold-Zeilen (Nicht-Ziel laut Spec: Bronze/Silver/Gold-
  Schichtung ist Sache von `[[datenqualitaet]]`). Das Ergebnis ist je Titel
  ein `SignalBuendel` mit mindestens `liquiditaet` und `volatilitaet`.

**`liquiditaet`/`volatilitaet` — provisorische Berechnung (Spec-Präzisierung,
siehe `docs/specs/dateneingang.md` "Verträge"):** Weder eine dedizierte
Volumen-/ADV-Quelle noch das für echte annualisierte Volatilität vorgesehene
`domain/quant`-Modul (ADR-009, architecture.md §8 — Eigenbau TA/Risiko,
noch nicht gebaut) existieren im MVP. Bis dahin gilt EIN klar benannter,
konfigurationsfreier Platzhalter-Default (analog den übrigen als
"provisorisch" markierten Defaults dieser Spec, z. B. AC4/AC10/AC11/AC12):

- `liquiditaet` = Anzahl der Quellen, die für den Titel mindestens einen
  Gold-Datenpunkt beigetragen haben (Datenverfügbarkeits-Proxy — NICHT die
  in `docs/data-model.md` (`instrument.liquiditaet`) referenzierte
  ADV/RVOL-Kennzahl).
- `volatilitaet` = Populationsstandardabweichung aller aggregierten
  `angereicherter_wert`-Werte (über alle passenden Quellen und deren
  komplette bisher persistierte Gold-Historie für den Titel) — kein
  annualisiertes ATR-Mass.

Beide Werte sind bewusst KEINE Score-/Kategorie-Berechnung (Nicht-Ziel:
"Score-/Kategorie-Berechnung erfolgt in der Analyse, nicht in der
Datenquellen-Abfrage") — sie sind reine Aggregations-/Streuungsmasse über
bereits validierte, geerdete Daten, keine Bewertung.
"""

from __future__ import annotations

import statistics
import uuid
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.contracts.dateneingang import (
    QuellenMetadatum,
    Signal,
    SignalBuendel,
    SignalBuendelAnfrage,
)
from app.db.models import DataSource, DataSourceAssetClass, MarketDataGold


def hole_signal_buendel(session: Session, anfrage: SignalBuendelAnfrage) -> list[SignalBuendel]:
    """AC7/AC8: DIE EINE geteilte Datenquellen-Abfrage-Schnittstelle.

    Liefert für jede `TitelAnfrage` in `anfrage.titel_anfragen` genau ein
    `SignalBuendel` (gleiche Reihenfolge wie im Input). Findet die Registry
    für die Anlageklasse eines Titels keine aktive Quelle mit persistierten
    Gold-Daten, ist das zurückgegebene Bündel strukturell leer (`signale=[]`,
    `liquiditaet=None`, `volatilitaet=None`, `quellen_metadaten=[]`) — es
    wird kein Wert geschätzt (analog AC2-Prinzip "fehlend kennzeichnen statt
    schätzen").
    """
    return [
        _signal_buendel_fuer_titel(
            session, titel=titel_anfrage.titel, anlageklasse=titel_anfrage.anlageklasse
        )
        for titel_anfrage in anfrage.titel_anfragen
    ]


def _signal_buendel_fuer_titel(session: Session, *, titel: str, anlageklasse: int) -> SignalBuendel:
    signale: list[Signal] = []
    quellen_metadaten: list[QuellenMetadatum] = []
    alle_werte: list[Decimal] = []

    for quelle in _passende_quellen(session, anlageklasse=anlageklasse):
        gold_reihe = _gold_historie(session, data_source_id=quelle.id, symbol=titel)
        if not gold_reihe:
            continue

        neueste = gold_reihe[-1]
        signale.append(
            Signal(
                quelle=quelle.name,
                wert=neueste.angereicherter_wert,
                qualitaetsindikator=neueste.qualitaetsindikator,
                beobachtet_am=neueste.observed_at,
            )
        )
        quellen_metadaten.append(
            QuellenMetadatum(
                data_source_id=quelle.id,
                name=quelle.name,
                kategorie=quelle.kategorie,
                beobachtet_am=neueste.observed_at,
            )
        )
        alle_werte.extend(zeile.angereicherter_wert for zeile in gold_reihe)

    return SignalBuendel(
        titel=titel,
        anlageklasse=anlageklasse,
        signale=signale,
        liquiditaet=Decimal(len(signale)) if signale else None,
        volatilitaet=_provisorische_volatilitaet(alle_werte),
        quellen_metadaten=quellen_metadaten,
    )


def _passende_quellen(session: Session, *, anlageklasse: int) -> list[DataSource]:
    """AC8 "wählt anhand der Anlageklassen-Zuordnung aus der Registry die
    passenden Quellen": nur Quellen, die die Registry (`DataSourceAssetClass`,
    AC5/AC6) dieser Anlageklasse zuordnet UND die aktiv sind (AC13-
    Kostentoggle), kommen in Frage — eine deaktivierte Quelle hat strukturell
    keine Gold-Daten (der Ingest respektiert den Aktiv-Schalter, S-020), ihr
    Ausschluss hier ist defensiv und macht die Auswahl unabhängig von diesem
    strukturellen Zusammenhang nachvollziehbar."""
    return list(
        session.execute(
            select(DataSource)
            .join(DataSourceAssetClass, DataSourceAssetClass.data_source_id == DataSource.id)
            .where(
                DataSourceAssetClass.asset_class_id == anlageklasse,
                DataSource.aktiv.is_(True),
            )
            .order_by(DataSource.name)
        )
        .scalars()
        .all()
    )


def _gold_historie(
    session: Session, *, data_source_id: uuid.UUID, symbol: str
) -> list[MarketDataGold]:
    """Liest die komplette persistierte Gold-Historie einer Quelle für einen
    Titel, älteste zuerst (reine Lese-Aggregation, AC8 — keine neue
    Bronze/Silver/Gold-Zeile entsteht hier)."""
    return list(
        session.execute(
            select(MarketDataGold)
            .where(
                MarketDataGold.data_source_id == data_source_id,
                MarketDataGold.symbol == symbol,
            )
            .order_by(MarketDataGold.observed_at.asc())
        )
        .scalars()
        .all()
    )


def _provisorische_volatilitaet(werte: list[Decimal]) -> Decimal | None:
    """Siehe Modul-Docstring: provisorischer Platzhalter (Populations-
    Standardabweichung), bis `domain/quant` (ADR-009) eine echte
    annualisierte Volatilität liefert. `None` ohne jeden Datenpunkt (nicht
    schätzen), `0` bei genau einem Datenpunkt (Streuung ist per Definition
    0, kein fehlender Wert)."""
    if not werte:
        return None
    if len(werte) == 1:
        return Decimal("0")
    return Decimal(str(statistics.pstdev(float(wert) for wert in werte)))


__all__ = ["hole_signal_buendel"]
