"""Broker-Port für den Order-Ausführungs-Kern (Story S-046, Spec
`docs/specs/ausfuehrung-paper.md` AC4, architecture.md §4: "abstrakte
Protokolle in `app/domain/**/ports.py`", P1).

Der reine Domain-Kern (`app.domain.execution.order_ausfuehrung`) darf laut
P1/P3 kein Netzwerk-I/O ausführen — er sendet eine `OrderAnfrage`
ausschliesslich über dieses `Protocol`; die konkreten Implementierungen
liegen in `app.adapters.brokers` (S-046: `IbkrPaperBrokerAdapter`,
`KryptoSimBrokerAdapter` — beide MVP-Paper-Simulationen, siehe dortiger
Moduldocstring). Ein künftiger "echt"-Adapter (Nicht-Ziel des MVP) würde
denselben Port implementieren — AC4 ("derselbe Order-Code-Pfad ... nicht
in getrennter Order-Logik") ist damit strukturell erzwungen: der
Domain-Kern kennt nur dieses eine `Protocol`, nie eine konkrete
Broker-Implementierung.

**S-048 ergänzt** (AC7/AC8, Fill-Handling):

- `BrokerPort.ermittle_fill` — die rohe Fill-Meldung EINER bereits
  angenommenen `OrderAnfrage` (Teilfill/Reject/Timeout, E1-E3). Bewusst
  eine EIGENE Methode statt einer Erweiterung von `platziere_order`/
  `OrderBestaetigung` (deren Vertrag laut `app.contracts.ausfuehrung_paper`
  bewusst auf die reine Order-ANNAHME beschränkt bleibt) — die
  Slippage-Berechnung und die Restmengen-Entscheidung (E1, "je Order-Typ")
  bleiben Domain-Sache (`app.domain.execution.order_ausfuehrung
  .verarbeite_fill`), der Adapter liefert nur die rohen Fakten
  (`BrokerFillMeldung`).
- `ExecutionRepository` — Persistenz-Port für die Order-Lifecycle-Zustände
  (`order`/`trade_fill`, data-model.md §4, C-016) — analog zu
  `app.domain.portfolio.ports.PositionRepository.schreibe_transaktion`
  (Depotmodul), hier für die Order-Ausführungs-eigene TCA (C-016, getrennt
  von der Depot-`transaction`-Historie, C-017)."""

from __future__ import annotations

from decimal import Decimal
from typing import Protocol
from uuid import UUID

from app.contracts.ausfuehrung_paper import (
    Ausfuehrungsergebnis,
    BrokerFillMeldung,
    OrderAnfrage,
    OrderBestaetigung,
)


class BrokerPort(Protocol):
    """Sendet eine bereits vereinheitlichte `OrderAnfrage` an einen
    Order-Endpunkt und liefert die Annahme-Bestätigung (AC1/AC5) —
    Fill-/Reject-/Timeout-Verarbeitung (AC7/AC8) über `ermittle_fill`
    (S-048)."""

    def platziere_order(self, anfrage: OrderAnfrage) -> OrderBestaetigung:
        """Nimmt `anfrage` entgegen und liefert die Annahme-Bestätigung
        des Endpunkts."""
        ...

    def ermittle_fill(
        self, anfrage: OrderAnfrage, bestaetigung: OrderBestaetigung, *, arrival_price: Decimal
    ) -> BrokerFillMeldung:
        """AC7/AC8 (S-048): liefert die rohe Fill-Meldung (Status, Menge,
        Preis, Kosten) für eine zuvor über `platziere_order` angenommene
        Order — OHNE Slippage-Berechnung oder Restmengen-Entscheidung
        (Domain-Sache, siehe `app.domain.execution.order_ausfuehrung
        .verarbeite_fill`). `arrival_price` wird durchgereicht, da eine
        MVP-Paper-Simulation (kein echtes Order-Buch, kein Live-Kurs-Zugriff
        im Adapter selbst) für Market-Orders (`anfrage.preis is None`)
        keinen anderen Referenzpreis kennt, zu dem sie "füllen" könnte."""
        ...


class ExecutionRepository(Protocol):
    """Persistiert die Order-Lifecycle-Zustände (`order`/`trade_fill`,
    data-model.md §4, C-016) — Grundlage der Order-Ausführungs-eigenen TCA
    (AC7/AC8, S-048)."""

    def speichere_ausfuehrung(
        self,
        anfrage: OrderAnfrage,
        ergebnis: Ausfuehrungsergebnis,
        *,
        instrument_id: UUID,
        platform_id: UUID | None = None,
    ) -> None:
        """AC7/AC8: legt eine `order`-Zeile mit dem in `ergebnis.status`
        ermittelten Endzustand an; NUR bei `status ∈ {"filled", "partial"}`
        zusätzlich eine `trade_fill`-Zeile (BR-139: kein Fill-Eintrag bei
        `"rejected"`/`"timeout"` — kein Bestand wird ohne bestätigten Fill
        verändert)."""
        ...


__all__ = ["BrokerPort", "ExecutionRepository"]
