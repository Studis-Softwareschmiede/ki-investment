"""Paper-Broker-Adapter (Story S-046, Spec `docs/specs/ausfuehrung-paper.md`
AC1/AC5, architecture.md §4 `app/adapters/brokers/`: "Broker-Port:
paper/live/sim (IBKR-Paper MVP; sim für brokerlose Krypto)").

Beide Implementierungen sind reine, deterministische MVP-Paper-
Simulationen — kein Netzwerk-I/O, keine echte IBKR-/Broker-Anbindung
(Nicht-Ziel der Spec: "Kein Live-/Echtgeld-Handel im MVP (nur Paper)").
`platziere_order` liefert ausschliesslich die Annahme-Bestätigung einer
`OrderAnfrage` (`OrderBestaetigung`, siehe `app.contracts.ausfuehrung_paper`-
Docstring) — keinen Fill-Preis, keinen Status jenseits der Annahme.

`IbkrPaperBrokerAdapter` und `KryptoSimBrokerAdapter` unterscheiden sich
ausschliesslich im zurückgemeldeten `broker_endpunkt_typ` (AC5) — beide
implementieren denselben `app.domain.execution.ports.BrokerPort` und
werden von `app.domain.execution.order_ausfuehrung.fuehre_order_aus`
identisch aufgerufen (AC4: der Unterschied liegt einzig im injizierten
Adapter, nicht in separater Order-Logik).

**S-048 ergänzt** `ermittle_fill` (AC7/AC8): die MVP-Paper-Simulation
"füllt" jede angenommene Order deterministisch VOLLSTÄNDIG (`status=
"filled"`) zum bereits bekannten Preis (`anfrage.preis`, sofern gesetzt —
Limit/Stop/Stop-Limit; sonst `arrival_price` als einziger für die
Simulation verfügbarer Referenzpreis bei einer Market-Order — Nicht-Ziel
dieser Story: ein eigenes Slippage-/Spread-Modell, das den Fill-Preis vom
Signal-Kurs abweichen liesse, ist AC9/S-049) ohne Kosten
(`tatsaechliche_kosten=0` — die eigentliche Kostenberechnung ist die
Plattform-Pre-Trade-Kalkulation, AC10/AC11, S-017, nicht Teil dieser
Fill-Meldung). Teilfill/Reject/Timeout (E1-E3) treten in dieser
deterministischen Happy-Path-Simulation strukturell nie auf — die
domain-seitige Verarbeitung dieser drei Fälle
(`app.domain.execution.order_ausfuehrung.verarbeite_fill`, AC7/AC8) ist
unabhängig von dieser Simulation vollständig getestet (Fake-`BrokerPort`,
siehe `tests/domain/execution/test_order_ausfuehrung_fill.py`)."""

from __future__ import annotations

import uuid
from decimal import Decimal

from app.contracts.ausfuehrung_paper import (
    BrokerEndpunktTyp,
    BrokerFillMeldung,
    OrderAnfrage,
    OrderBestaetigung,
)


class _PaperBrokerAdapter:
    """Gemeinsame Basis beider MVP-Paper-Endpunkte — erzeugt eine
    `OrderBestaetigung`, die die `OrderAnfrage` echofasst und um eine
    generierte `order_id` sowie den fest zugewiesenen
    `broker_endpunkt_typ` ergänzt."""

    def __init__(self, *, broker_endpunkt_typ: BrokerEndpunktTyp) -> None:
        self._broker_endpunkt_typ = broker_endpunkt_typ

    def platziere_order(self, anfrage: OrderAnfrage) -> OrderBestaetigung:
        return OrderBestaetigung(
            order_id=str(uuid.uuid4()),
            broker_endpunkt_typ=self._broker_endpunkt_typ,
            titel_id=anfrage.titel_id,
            richtung=anfrage.richtung,
            order_typ=anfrage.order_typ,
            groesse=anfrage.groesse,
            preis=anfrage.preis,
        )

    def ermittle_fill(
        self, anfrage: OrderAnfrage, bestaetigung: OrderBestaetigung, *, arrival_price: Decimal
    ) -> BrokerFillMeldung:
        """AC7/AC8 (S-048): deterministischer Happy-Path — vollständiger
        Fill zum bereits bekannten Preis (`anfrage.preis`, sonst
        `arrival_price`), siehe Moduldocstring."""
        fill_preis = anfrage.preis if anfrage.preis is not None else arrival_price
        return BrokerFillMeldung(
            status="filled",
            ausgefuehrte_menge=anfrage.groesse,
            fill_preis=fill_preis,
            tatsaechliche_kosten=Decimal("0"),
        )


class IbkrPaperBrokerAdapter(_PaperBrokerAdapter):
    """AC5-Default-Endpunkt: Interactive Brokers im Paper-Modus (MVP-
    Broker-Anbindung)."""

    def __init__(self) -> None:
        super().__init__(broker_endpunkt_typ="ibkr_paper")


class KryptoSimBrokerAdapter(_PaperBrokerAdapter):
    """AC5/A3-Fallback-Endpunkt: brokerlose Krypto-Simulation, sofern für
    die betreffende Anlageklasse kein Broker angebunden ist
    (`app.domain.execution.order_ausfuehrung.bestimme_broker_endpunkt_typ`)."""

    def __init__(self) -> None:
        super().__init__(broker_endpunkt_typ="krypto_sim_brokerless")


__all__ = ["IbkrPaperBrokerAdapter", "KryptoSimBrokerAdapter"]
