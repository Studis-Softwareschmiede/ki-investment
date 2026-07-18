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
"filled"`) ohne Kosten (`tatsaechliche_kosten=0` — die eigentliche
Kostenberechnung ist die Plattform-Pre-Trade-Kalkulation, AC10/AC11,
S-017, nicht Teil dieser Fill-Meldung). Teilfill/Reject/Timeout (E1-E3)
treten in dieser deterministischen Happy-Path-Simulation strukturell nie
auf — die domain-seitige Verarbeitung dieser drei Fälle
(`app.domain.execution.order_ausfuehrung.verarbeite_fill`, AC7/AC8) ist
unabhängig von dieser Simulation vollständig getestet (Fake-`BrokerPort`,
siehe `tests/domain/execution/test_order_ausfuehrung_fill.py`).

**S-049 ergänzt** das AC9/A2-Slippage-/Spread-Modell: `ermittle_fill`
füllt NICHT mehr unverändert zum Referenzpreis (`anfrage.preis`, sofern
gesetzt — Limit/Stop/Stop-Limit; sonst `arrival_price` als einziger für
die Simulation verfügbarer Referenzpreis bei einer Market-Order), sondern
wendet über `berechne_paper_fill_preis` einen eigenen, deterministischen
Slippage-/Spread-Aufschlag an (Spec A2: "Paper-Fills sind sonst zu
optimistisch") — Käufe füllen teurer, Verkäufe günstiger als der
Referenzpreis. Die zwei Prozent-Parameter (`spread_pct`/`slippage_pct`)
sind je Adapter-Instanz konfigurierbar (Konstruktor-Parameter, Default aus
`Settings.paper_fill_spread_pct_default`/`paper_fill_slippage_pct_default`,
AC9 "provisorischer, konfigurierbarer Default") und rein additiv — kein
`random`/keine Systemzeit im Modell (P3-Determinismus: gleiche Eingabe
liefert immer denselben Fill-Preis)."""

from __future__ import annotations

import uuid
from decimal import ROUND_HALF_UP, Decimal

from app.config import get_settings
from app.contracts.ausfuehrung_paper import (
    BrokerEndpunktTyp,
    BrokerFillMeldung,
    OrderAnfrage,
    OrderBestaetigung,
    OrderRichtung,
)

#: Rundungsraster für Preise (NUMERIC(20,8), P7/ADR-010) — kaufmännisch
#: (ROUND_HALF_UP), analog `order_ausfuehrung._quantize_geld` (S-041/S-053-
#: Lesson: Geld-Felder werden an der Schreibgrenze quantisiert, nicht in
#: der reinen Formel selbst).
_GELD_QUANTUM = Decimal("0.00000001")


def _quantize_geld(wert: Decimal) -> Decimal:
    return wert.quantize(_GELD_QUANTUM, rounding=ROUND_HALF_UP)


def berechne_paper_fill_preis(
    referenzpreis: Decimal,
    *,
    richtung: OrderRichtung,
    spread_pct: Decimal,
    slippage_pct: Decimal,
) -> Decimal:
    """AC9/A2: eigenes, deterministisches Paper-Fill-Slippage-/Spread-Modell
    — verschiebt `referenzpreis` um `(spread_pct + slippage_pct) / 100`,
    richtungsabhängig: bei `richtung="kauf"` nach OBEN (teurer), bei
    `richtung="verkauf"` nach UNTEN (günstiger) — ein Paper-Fill "zu
    optimistisch" zum unveränderten Signal-Kurs (A2) wird damit vermieden.
    `spread_pct`/`slippage_pct` sind Prozent-Zahlen (analog
    `Settings.erwartete_slippage_pct_default` — NICHT als Anteil 0-1 zu
    lesen); beide `>= 0`, `spread_pct=0` UND `slippage_pct=0` liefert den
    unveränderten Referenzpreis. Rein deterministisch (kein `random`, keine
    Systemzeit) — an der NUMERIC(20,8)-Schreibgrenze quantisiert."""
    gesamt_faktor = (spread_pct + slippage_pct) / Decimal("100")
    vorzeichen = Decimal("1") if richtung == "kauf" else Decimal("-1")
    return _quantize_geld(referenzpreis * (Decimal("1") + vorzeichen * gesamt_faktor))


class _PaperBrokerAdapter:
    """Gemeinsame Basis beider MVP-Paper-Endpunkte — erzeugt eine
    `OrderBestaetigung`, die die `OrderAnfrage` echofasst und um eine
    generierte `order_id` sowie den fest zugewiesenen
    `broker_endpunkt_typ` ergänzt.

    `spread_pct`/`slippage_pct` (AC9, S-049) sind optionale Overrides des
    Paper-Fill-Slippage-/Spread-Modells; `None` (Default) liest die
    provisorischen `Settings`-Defaults beim Instanziieren."""

    def __init__(
        self,
        *,
        broker_endpunkt_typ: BrokerEndpunktTyp,
        spread_pct: Decimal | None = None,
        slippage_pct: Decimal | None = None,
    ) -> None:
        self._broker_endpunkt_typ = broker_endpunkt_typ
        einstellungen = get_settings()
        self._spread_pct = (
            spread_pct
            if spread_pct is not None
            else Decimal(str(einstellungen.paper_fill_spread_pct_default))
        )
        self._slippage_pct = (
            slippage_pct
            if slippage_pct is not None
            else Decimal(str(einstellungen.paper_fill_slippage_pct_default))
        )

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
        """AC7/AC8 (S-048) + AC9 (S-049): deterministischer Happy-Path-Fill
        — der Referenzpreis (`anfrage.preis`, sonst `arrival_price`) wird
        über `berechne_paper_fill_preis` um das konfigurierte Slippage-/
        Spread-Modell verschoben, siehe Moduldocstring."""
        referenzpreis = anfrage.preis if anfrage.preis is not None else arrival_price
        fill_preis = berechne_paper_fill_preis(
            referenzpreis,
            richtung=anfrage.richtung,
            spread_pct=self._spread_pct,
            slippage_pct=self._slippage_pct,
        )
        return BrokerFillMeldung(
            status="filled",
            ausgefuehrte_menge=anfrage.groesse,
            fill_preis=fill_preis,
            tatsaechliche_kosten=Decimal("0"),
        )


class IbkrPaperBrokerAdapter(_PaperBrokerAdapter):
    """AC5-Default-Endpunkt: Interactive Brokers im Paper-Modus (MVP-
    Broker-Anbindung)."""

    def __init__(
        self, *, spread_pct: Decimal | None = None, slippage_pct: Decimal | None = None
    ) -> None:
        super().__init__(
            broker_endpunkt_typ="ibkr_paper", spread_pct=spread_pct, slippage_pct=slippage_pct
        )


class KryptoSimBrokerAdapter(_PaperBrokerAdapter):
    """AC5/A3-Fallback-Endpunkt: brokerlose Krypto-Simulation, sofern für
    die betreffende Anlageklasse kein Broker angebunden ist
    (`app.domain.execution.order_ausfuehrung.bestimme_broker_endpunkt_typ`)."""

    def __init__(
        self, *, spread_pct: Decimal | None = None, slippage_pct: Decimal | None = None
    ) -> None:
        super().__init__(
            broker_endpunkt_typ="krypto_sim_brokerless",
            spread_pct=spread_pct,
            slippage_pct=slippage_pct,
        )


__all__ = ["IbkrPaperBrokerAdapter", "KryptoSimBrokerAdapter", "berechne_paper_fill_preis"]
