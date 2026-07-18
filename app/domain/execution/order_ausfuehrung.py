"""Order-Ausführungs-Kern: Kauf+Verkauf, gemeinsamer Code-Pfad, Order-Typen
(Story S-046, Spec `docs/specs/ausfuehrung-paper.md` AC1/AC4/AC5/AC6).

Reiner Domain-Kern (architecture.md §4 P1/P3): keine I/O, kein LLM, keine
DB — Zugriff auf den Broker-Endpunkt ausschliesslich über den
`app.domain.execution.ports.BrokerPort`-Port (injiziert, Hexagonal
Ports & Adapters). Deckt:

- **AC1** — `erstelle_order_anfrage_fuer_kauf`/`_fuer_verkauf`
  normalisieren die beiden bestehenden Modul-Ausgänge — die gebilligte
  Kauf-Order des Risikomanagement-Gates (`AnnotierteKaufOrder` +
  `GateEntscheid`, S-040/S-044) bzw. den Verkaufsauftrag des Exit-Sizings
  (`Verkaufsauftrag`, S-042/S-055) — auf das gemeinsame `OrderAnfrage`-
  DTO; `fuehre_order_aus` führt jede einzelne `OrderAnfrage` über
  denselben Aufruf aus. `_fuer_kauf` liefert genau EINE `OrderAnfrage`;
  `_fuer_verkauf` liefert eine LISTE von `OrderAnfrage` — eine je
  `auftrag.tranchen`-Element (Tranchierung aus S-042/S-055 bleibt
  erhalten, siehe `erstelle_order_anfrage_fuer_verkauf`-Docstring), bei
  `ausfuehrungsprofil="sofort"` eine 1-Element-Liste.

- **AC4** — `fuehre_order_aus` ist der GEMEINSAME Order-Code-Pfad: die
  Funktion selbst enthält keine Fallunterscheidung nach Order-Quelle
  (Kauf/Verkauf) oder Modus (echt/simuliert) — sie wählt nur den
  Broker-ENDPUNKT-TYP (AC5) und delegiert an den dafür injizierten
  `BrokerPort`. Der "Unterschied ... allein in Endpunkt/Zugangsschlüssel"
  (Spec-Wortlaut) ist damit strukturell abgebildet: ein künftiger
  "echt"-Modus (Nicht-Ziel des MVP, spätere Story S-047 für die
  Modus-Auflösung selbst) würde ausschliesslich einen anderen
  `BrokerPort` an DIESELBE Funktion übergeben, nie eine eigene
  Order-Logik.

- **AC5** — `bestimme_broker_endpunkt_typ` wählt deterministisch
  zwischen `"ibkr_paper"` (Default, Broker angebunden) und
  `"krypto_sim_brokerless"` (keine Broker-Anbindung, deckt A3) — anhand
  der konfigurierbaren `BrokerRoutingKonfiguration.
  brokerlose_anlageklassen_ids` (Default Krypto, architecture.md P6: kein
  hartkodierter `if asset_class == 7`-Zweig). Dies ist eine EIGENSTÄNDIGE
  Routing-Entscheidung ("welche Broker-Port-IMPLEMENTIERUNG spricht die
  Order an"), unabhängig von der bereits bestehenden S-017-Plattform-
  Auswahl (`app.db.trading_platform.waehle_plattform_fuer_anlageklasse`,
  AC10 — welche Plattform die PRE-TRADE-KOSTEN-Referenzdaten liefert):
  im MVP existiert genau EIN Broker (Interactive Brokers, Paper), eine
  dynamische Mehr-Broker-Registry ist Nicht-Ziel dieser Story.

- **AC6** — beide `erstelle_order_anfrage_*`-Funktionen reichen den vom
  Aufrufer (Kauf) bzw. vom Verkaufsauftrag (Verkauf, gemappt über
  `_VERKAUF_ORDER_TYP_MAP`) übergebenen Order-Typ unverändert in die
  `OrderAnfrage` durch — der volle AC6-Wertebereich (Market, Limit, Stop,
  Stop-Limit, Trailing, TWAP, `ExecutionOrderTyp`) durchläuft denselben
  Code-Pfad ohne Sonderbehandlung einzelner Typen (kein `if order_typ ==
  ...`-Zweig in `fuehre_order_aus`); die tatsächliche Order-Typ-spezifische
  Übersetzung in ein Broker-API-Feld liegt beim jeweiligen
  `BrokerPort`-Adapter (Nicht-Ziel des Domain-Kerns, P1: kein Broker-
  API-Wissen im Kern).

`AnnotierteKaufOrder`/`GateEntscheid` (S-040/S-044) tragen bislang keinen
Order-Typ/Preis (die Position-/Risiko-Sizing-Kette dieser Codebasis
liefert nur eine CHF-Grösse, siehe `OrderAnfrage.groesse`-Docstring) —
`order_typ`/`preis` kommen deshalb hier als explizite Parameter herein,
die ein künftiger Orchestrierungs-Layer (`app.orchestration.buy_pipeline`,
noch nicht gebaut) beisteuert.

**S-047 ergänzt** `bestimme_wirksamen_modus` (AC2/AC3, BR-019):

- **AC2** — löst den wirksamen Modus «echt/simuliert» einer Order anhand
  `ModusKonfiguration` auf: die spezifischste gesetzte Ebene gewinnt
  (`modus_je_anlageklasse[asset_class_id]`, falls vorhanden, sonst
  `global_modus`, Spec A1) — strukturell identisch zum bereits
  bestehenden Auflösungsmuster von `bestimme_broker_endpunkt_typ` (AC5,
  global-Default + Anlageklassen-Override statt hartkodierter
  Code-Grenze, P6).
- **AC3/BR-019** — ist der aufgelöste Modus NICHT `"simuliert"` (Allowlist,
  Review-Fix: fail-closed statt der ursprünglichen `"echt"`-Denylist, die
  einen unbekannten Fremdwert unbemerkt hätte durchrutschen lassen),
  wirft die Funktion `LiveModusGesperrtError` statt still auf
  `"simuliert"` herunterzustufen: "Im MVP ist ausschliesslich der
  simulierte (Paper-)Modus aktiv" (AC3) bzw. "Live ist gesperrt" (BR-019)
  ist eine harte MVP-Grenze (Nicht-Ziel "Kein Live-/Echtgeld-Handel im
  MVP") — eine fälschlich auf `"echt"` konfigurierte Ebene soll laut
  blockiert werden, nicht unbemerkt auf Paper umgeleitet. Das "voll
  autonom, keine Bestätigungsabfrage vor der Order" aus AC3 ist
  strukturell erfüllt, da weder diese Funktion noch `fuehre_order_aus`
  einen Bestätigungs-/Freigabe-Parameter kennen.

  Review-Fix (Sicherheit): `bestimme_wirksamen_modus` ist NICHT mehr
  standalone — `fuehre_order_aus` ruft sie VOR jeder Broker-Übermittlung
  auf (siehe dortiger Docstring). Ursprünglich (S-046/S-047-Erstfassung)
  hatte die Funktion keinen Aufrufer im Order-Pfad; die MVP-Live-Sperre
  griff nur zufällig, weil (noch) kein `"echt"`-`BrokerPort`-Adapter
  existiert (Nicht-Ziel des MVP) — nicht durch eine aktive Prüfung. Ein
  künftiger Live-Adapter wäre damit ohne weitere Sperre erreichbar
  gewesen."""

from __future__ import annotations

from decimal import Decimal

from app.contracts.ausfuehrung_paper import (
    BrokerEndpunktTyp,
    BrokerRoutingKonfiguration,
    ExecutionOrderTyp,
    ModusKonfiguration,
    OrderAnfrage,
    OrderBestaetigung,
)
from app.contracts.depot import Modus
from app.contracts.risikomanagement import GateEntscheid
from app.contracts.sizing import OrderTyp as VerkaufOrderTyp
from app.contracts.sizing import Verkaufsauftrag
from app.contracts.strategie_exit_regeln import AnnotierteKaufOrder
from app.domain.execution.ports import BrokerPort

#: AC1/AC6: mappt die 4 von `app.domain.sizing.exit_sizing` erzeugbaren
#: Verkaufs-Order-Typen (`app.contracts.sizing.OrderTyp`) auf den vollen
#: AC6-Wertebereich (`ExecutionOrderTyp`) — `"stop_market"` (Sizing-Wortlaut
#: "Fill sicher, Preis nicht") entspricht AC6s `"stop"` (ein Stop-Order,
#: der bei Auslösung zum Market wird, im Unterschied zu `"stop_limit"`);
#: die übrigen 3 Typen sind namensgleich.
_VERKAUF_ORDER_TYP_MAP: dict[VerkaufOrderTyp, ExecutionOrderTyp] = {
    "market": "market",
    "limit": "limit",
    "stop_market": "stop",
    "twap": "twap",
}


class LiveModusGesperrtError(ValueError):
    """AC3/BR-019 (S-047): der aufgelöste Modus einer Order ist `"echt"`,
    was im MVP hart gesperrt ist ("Kein Live-/Echtgeld-Handel im MVP",
    Nicht-Ziel) — geworfen von `bestimme_wirksamen_modus` statt eines
    stillen Downgrades auf `"simuliert"`."""


def bestimme_wirksamen_modus(
    asset_class_id: int, *, konfiguration: ModusKonfiguration | None = None
) -> Modus:
    """AC2/AC3: löst den wirksamen Modus «echt/simuliert» einer Order auf
    — die spezifischste gesetzte Ebene gewinnt
    (`konfiguration.modus_je_anlageklasse[asset_class_id]`, falls
    vorhanden, sonst `konfiguration.global_modus`, Spec A1).

    Review-Fix (Sicherheit, fail-closed statt fail-open): die Sperre ist
    eine ALLOWLIST — ausschliesslich `"simuliert"` wird durchgelassen,
    JEDER andere aufgelöste Wert (inkl. `"echt"` sowie ein etwaiger,
    nicht via `Modus`-Literal konstruierbarer Fremdwert) wirft. Eine
    Denylist (`if ... == "echt": raise`) hätte einen unbekannten Wert
    unbemerkt durchgelassen — für ein Sicherheits-Gate ist "alles ausser
    dem explizit erlaubten Wert sperren" die richtige Grundhaltung.

    Raises:
        LiveModusGesperrtError: der aufgelöste Modus ist NICHT
            `"simuliert"` — im MVP ausschliesslich `"simuliert"` aktiv
            (AC3, BR-019 "Live ist gesperrt")."""
    aktive_konfiguration = konfiguration or ModusKonfiguration()
    aufgeloester_modus = aktive_konfiguration.modus_je_anlageklasse.get(
        asset_class_id, aktive_konfiguration.global_modus
    )
    if aufgeloester_modus != "simuliert":
        raise LiveModusGesperrtError(
            f"Modus {aufgeloester_modus!r} fuer asset_class_id={asset_class_id} ist im "
            "MVP hart gesperrt (BR-019, Nicht-Ziel: kein Live-/Echtgeld-Handel im MVP) "
            "- nur 'simuliert' ist aktiv (Allowlist: fail-closed statt fail-open)."
        )
    return aufgeloester_modus


def bestimme_broker_endpunkt_typ(
    asset_class_id: int, *, konfiguration: BrokerRoutingKonfiguration | None = None
) -> BrokerEndpunktTyp:
    """AC5: `"krypto_sim_brokerless"`, wenn `asset_class_id` in der
    konfigurierten `brokerlose_anlageklassen_ids`-Menge liegt (Default nur
    Krypto, `DEFAULT_BROKERLOSE_ANLAGEKLASSEN_IDS`); sonst der MVP-Default
    `"ibkr_paper"`."""
    aktive_konfiguration = konfiguration or BrokerRoutingKonfiguration()
    if asset_class_id in aktive_konfiguration.brokerlose_anlageklassen_ids:
        return "krypto_sim_brokerless"
    return "ibkr_paper"


def erstelle_order_anfrage_fuer_kauf(
    kauf_order: AnnotierteKaufOrder,
    gate_entscheid: GateEntscheid,
    *,
    asset_class_id: int,
    order_typ: ExecutionOrderTyp,
    preis: Decimal | None = None,
) -> OrderAnfrage:
    """AC1: normalisiert eine gebilligte Kauf-Order (Risikomanagement-
    Gate, S-044) auf das gemeinsame `OrderAnfrage`-DTO.

    `order_typ`/`preis` kommen als explizite Parameter herein (siehe
    Moduldocstring — die Position-/Risiko-Sizing-Kette liefert bislang
    keinen Order-Typ für Käufe).

    Raises:
        ValueError: `gate_entscheid.entscheid == "blockieren"` oder
            `gate_entscheid.freigegebene_groesse <= 0` — ein blockierter
            bzw. grössenloser Kauf darf laut Gate-Entscheid nicht
            ausgeführt werden (AC6/AC12 der `risikomanagement.md`-Spec,
            hier als Vorbedingung dieses Order-Ausführungs-Kerns
            durchgesetzt).
    """
    if gate_entscheid.entscheid == "blockieren" or gate_entscheid.freigegebene_groesse <= 0:
        raise ValueError(
            "Kauf-Order kann nicht ausgeführt werden: Risikomanagement-Gate hat "
            f"nicht freigegeben (entscheid={gate_entscheid.entscheid!r}, "
            f"freigegebene_groesse={gate_entscheid.freigegebene_groesse!r}, "
            f"begruendung={gate_entscheid.begruendung!r})."
        )

    return OrderAnfrage(
        titel_id=kauf_order.titel_id,
        asset_class_id=asset_class_id,
        richtung="kauf",
        groesse=gate_entscheid.freigegebene_groesse,
        order_typ=order_typ,
        preis=preis,
    )


def erstelle_order_anfrage_fuer_verkauf(
    auftrag: Verkaufsauftrag, *, asset_class_id: int
) -> list[OrderAnfrage]:
    """AC1: normalisiert einen Verkaufsauftrag (Exit-Sizing, S-042/S-055)
    auf eine LISTE von `OrderAnfrage`-DTOs — eine je Element von
    `auftrag.tranchen` (Review-Fix: die volle `auftrag.menge` allein hätte
    bei `ausfuehrungsprofil="gestaffelt"` die Tranchierung aus S-042/S-055
    unterlaufen, da die GESAMTE Position in einer Order an den Broker
    gegangen wäre statt gestaffelt).

    Bei `ausfuehrungsprofil="sofort"` besteht `auftrag.tranchen` laut
    Vertrag (`Verkaufsauftrag`-Docstring) aus genau einem Element mit der
    vollen `menge` — die Rückgabe ist dann eine 1-Element-Liste, deren
    einzige `OrderAnfrage` bit-identisch zur bisherigen Einzel-Rückgabe
    ist. `order_typ`/`preis` kommen bereits vollständig vom Exit-Sizing
    (AC12: "kein Risikomanagement-Gate dazwischen", hier entsprechend
    keine zusätzliche Prüfung) und gelten unverändert für jede Tranche.

    Ein Aufrufer schickt jede Tranche einzeln durch `fuehre_order_aus`
    (AC4, der gemeinsame Order-Code-Pfad bleibt dabei unverändert — er
    führt weiterhin genau EINE `OrderAnfrage` je Aufruf aus)."""
    order_typ = _VERKAUF_ORDER_TYP_MAP[auftrag.order_typ]
    return [
        OrderAnfrage(
            titel_id=auftrag.titel_id,
            asset_class_id=asset_class_id,
            richtung="verkauf",
            groesse=tranche,
            order_typ=order_typ,
            preis=auftrag.preis,
        )
        for tranche in auftrag.tranchen
    ]


def fuehre_order_aus(
    anfrage: OrderAnfrage,
    *,
    ibkr_paper_port: BrokerPort,
    krypto_sim_port: BrokerPort,
    konfiguration: BrokerRoutingKonfiguration | None = None,
    modus_konfiguration: ModusKonfiguration | None = None,
) -> OrderBestaetigung:
    """AC1/AC4/AC5/AC6: der gemeinsame Order-Code-Pfad — identisch für
    Kauf UND Verkauf (AC1), identisch für jeden `ExecutionOrderTyp` (AC6,
    keine Typ-Fallunterscheidung), und identisch für "echt"/"simuliert"
    (AC4: einziger variabler Punkt ist WELCHER `BrokerPort` als
    `ibkr_paper_port`/`krypto_sim_port` injiziert wurde — diese Funktion
    selbst enthält keine Fallunterscheidung nach Order-Quelle Kauf/
    Verkauf; die AC2/AC3-Modus-Sperre unten gilt UNIFORM für jede
    `OrderAnfrage`, nicht als Kauf/Verkauf-spezifischer Zweig).

    Review-Fix (Sicherheit, AC2/AC3/BR-019): löst VOR jeder Broker-
    Übermittlung über `bestimme_wirksamen_modus` den wirksamen Modus der
    `anfrage.asset_class_id` auf und wirft `LiveModusGesperrtError`, wenn
    dieser nicht `"simuliert"` ist — kein `BrokerPort`-Aufruf erfolgt in
    diesem Fall. Vorher (S-046/S-047-Ursprungsfassung) war
    `bestimme_wirksamen_modus` standalone und hatte KEINEN Aufrufer im
    Order-Pfad; die MVP-Live-Sperre griff nur zufällig, weil (noch) kein
    `"echt"`-`BrokerPort`-Adapter existiert — nicht durch eine aktive
    Prüfung. Ein künftiger Live-Adapter wäre ohne diese Verdrahtung ohne
    weitere Sperre erreichbar gewesen.

    Wählt den Broker-Endpunkt-Typ deterministisch über
    `bestimme_broker_endpunkt_typ` (AC5) und delegiert die eigentliche
    Order-Übermittlung an den entsprechenden `BrokerPort`.

    Raises:
        LiveModusGesperrtError: der für `anfrage.asset_class_id`
            aufgelöste Modus ist nicht `"simuliert"` (AC3, BR-019)."""
    bestimme_wirksamen_modus(anfrage.asset_class_id, konfiguration=modus_konfiguration)
    endpunkt_typ = bestimme_broker_endpunkt_typ(anfrage.asset_class_id, konfiguration=konfiguration)
    port = krypto_sim_port if endpunkt_typ == "krypto_sim_brokerless" else ibkr_paper_port
    return port.platziere_order(anfrage)


__all__ = [
    "LiveModusGesperrtError",
    "bestimme_broker_endpunkt_typ",
    "bestimme_wirksamen_modus",
    "erstelle_order_anfrage_fuer_kauf",
    "erstelle_order_anfrage_fuer_verkauf",
    "fuehre_order_aus",
]
