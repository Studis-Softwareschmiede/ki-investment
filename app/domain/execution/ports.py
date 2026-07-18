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
Broker-Implementierung."""

from __future__ import annotations

from typing import Protocol

from app.contracts.ausfuehrung_paper import OrderAnfrage, OrderBestaetigung


class BrokerPort(Protocol):
    """Sendet eine bereits vereinheitlichte `OrderAnfrage` an einen
    Order-Endpunkt und liefert die Annahme-Bestätigung (AC1/AC5) —
    Fill-/Reject-/Timeout-Verarbeitung (AC7/AC8) ist NICHT Teil dieses
    Ports (eigene Folge-Story S-048)."""

    def platziere_order(self, anfrage: OrderAnfrage) -> OrderBestaetigung:
        """Nimmt `anfrage` entgegen und liefert die Annahme-Bestätigung
        des Endpunkts."""
        ...


__all__ = ["BrokerPort"]
