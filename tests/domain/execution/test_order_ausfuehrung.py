"""Tests für den Order-Ausführungs-Kern (Story S-046) + die S-047-
Modus-Auflösung (`bestimme_wirksamen_modus`).

Covers (ausfuehrung-paper): AC1, AC2, AC3, AC4, AC5, AC6

- AC1: `erstelle_order_anfrage_fuer_kauf`/`_fuer_verkauf` normalisieren
  sowohl eine gebilligte Kauf-Order (Risikomanagement-Gate) als auch einen
  Verkaufsauftrag (Exit-Sizing) auf das gemeinsame `OrderAnfrage`-DTO;
  `fuehre_order_aus` führt beide über denselben Aufruf aus. Eine
  blockierte/grössenlose Kauf-Order wird nicht in eine `OrderAnfrage`
  übersetzt (`ValueError`). `erstelle_order_anfrage_fuer_verkauf` liefert
  eine LISTE von `OrderAnfrage` — eine je `tranchen`-Element (Review-Fix:
  ein gestaffelter Verkaufsauftrag mit N Tranchen erzeugt N
  `OrderAnfrage`n, deren Mengen-Summe die volle Zielmenge ergibt, statt
  die Tranchierung durch Verwendung der vollen `menge` zu unterlaufen).
- AC4: `fuehre_order_aus` ist strukturell derselbe Code-Pfad für Kauf UND
  Verkauf sowie für beliebige injizierte `BrokerPort`-Implementierungen
  (kein `modus`-Parameter, keine Fallunterscheidung nach Order-Quelle) —
  per Signatur-Introspektion UND per Verhaltenstest mit zwei strukturell
  unterschiedlichen Fake-Ports belegt.
- AC5: `bestimme_broker_endpunkt_typ` routet Krypto (Default-Konfiguration)
  auf `"krypto_sim_brokerless"`, alle anderen Anlageklassen auf
  `"ibkr_paper"` — konfigurierbar über `BrokerRoutingKonfiguration`
  (P6, keine hartkodierte Anlageklassen-Grenze).
- AC6: alle 6 `ExecutionOrderTyp`-Werte (Market, Limit, Stop, Stop-Limit,
  Trailing, TWAP) durchlaufen `erstelle_order_anfrage_fuer_kauf`
  unverändert; `erstelle_order_anfrage_fuer_verkauf` mappt die 4 vom
  Exit-Sizing erzeugbaren `sizing.OrderTyp`-Werte korrekt (insbesondere
  `stop_market -> stop`).
- AC2 (S-047): `bestimme_wirksamen_modus` löst die spezifischste gesetzte
  Ebene auf — ein Anlageklassen-Override (`modus_je_anlageklasse`)
  gewinnt gegen `global_modus`, unabhängig davon, in welche Richtung
  (Override kann strenger ODER lockerer als Global sein); ohne Override
  fällt eine Anlageklasse auf `global_modus` zurück.
- AC3 (S-047): löst sich `"echt"` auf (global oder je Anlageklasse), wirft
  `LiveModusGesperrtError` — MVP-Sperre (BR-019 "Live ist gesperrt", kein
  stilles Downgrade auf `"simuliert"`). Der Default (keine Konfiguration)
  liefert `"simuliert"` ohne zu werfen. Strukturell: weder
  `bestimme_wirksamen_modus` noch `fuehre_order_aus` kennen einen
  Bestätigungs-/Freigabe-Parameter (voll autonom, keine
  Bestätigungsabfrage vor der Order).
- AC3 (Review-Fix, Sicherheit — Allowlist statt Denylist): die Sperre ist
  fail-closed — NICHT nur `"echt"` wird geblockt, sondern JEDER Wert
  ausser `"simuliert"`, auch ein Fremdwert ausserhalb des
  `Modus`-Literal-Wertebereichs (nur via Konstruktions-Umgehung
  erzeugbar, da der Kontrakt selbst per `Literal["echt", "simuliert"]`
  einschränkt).
- AC3 (Review-Fix, Sicherheit — aktive Verdrahtung): `fuehre_order_aus`
  ruft `bestimme_wirksamen_modus` VOR jeder `BrokerPort`-Übermittlung auf
  und wirft `LiveModusGesperrtError`, BEVOR der Port erreicht wird — die
  Sperre griff vorher nur zufällig (kein `"echt"`-Adapter existiert),
  jetzt durch eine aktive Prüfung im gemeinsamen Order-Pfad.
"""

from __future__ import annotations

import inspect
import uuid
from datetime import UTC, datetime
from decimal import Decimal
from types import MappingProxyType

import pytest

from app.contracts.ausfuehrung_paper import (
    BrokerRoutingKonfiguration,
    ExecutionOrderTyp,
    ModusKonfiguration,
    OrderAnfrage,
    OrderBestaetigung,
)
from app.contracts.risikomanagement import GateEntscheid
from app.contracts.sizing import Verkaufsauftrag
from app.contracts.strategie_exit_regeln import AnnotierteKaufOrder, ExitDefaultVorschlag
from app.domain.execution.order_ausfuehrung import (
    LiveModusGesperrtError,
    bestimme_broker_endpunkt_typ,
    bestimme_wirksamen_modus,
    erstelle_order_anfrage_fuer_kauf,
    erstelle_order_anfrage_fuer_verkauf,
    fuehre_order_aus,
)

_JETZT = datetime(2026, 7, 18, 10, 0, tzinfo=UTC)

_VORSCHLAG = ExitDefaultVorschlag(
    kategorie="value_aktien",
    stop_typ="fundamental",
    stop_hinweis="Fundamentaler Stop (These bricht).",
    stop_parameter=None,
    stop_unbestimmt=False,
    take_profit_hinweis="Zielwert erreicht.",
    time_box=None,
    thesis_invalidierung="Marktanteil < 10%.",
)


def _kauf_order(
    *, titel_id: str = "AAPL", ordergroesse: Decimal = Decimal("1000")
) -> AnnotierteKaufOrder:
    return AnnotierteKaufOrder(
        titel_id=titel_id,
        ordergroesse=ordergroesse,
        strategie="Value",
        zeithorizont=7,
        exit_regeln=_VORSCHLAG,
        these="Unterbewertet laut Analyse.",
        fixiert_am=_JETZT,
    )


def _gate_entscheid(
    *, entscheid: str = "durchwinken", freigegebene_groesse: Decimal = Decimal("1000")
) -> GateEntscheid:
    return GateEntscheid(
        entscheid=entscheid,
        freigegebene_groesse=freigegebene_groesse,
        begruendung="Test-Begründung.",
    )


def _verkaufsauftrag(*, order_typ: str = "limit", preis: Decimal | None = None) -> Verkaufsauftrag:
    return Verkaufsauftrag(
        titel_id="AAPL",
        menge=Decimal("10"),
        tranchen=(Decimal("10"),),
        order_typ=order_typ,
        preis=preis,
        ausfuehrungsprofil="gestaffelt",
        tranchen_trigger=None,
    )


class _FakeBrokerPort:
    """Test-Double des `BrokerPort`-Protocol — merkt sich die letzte
    Anfrage, ohne echtes I/O."""

    def __init__(self, *, broker_endpunkt_typ: str) -> None:
        self._broker_endpunkt_typ = broker_endpunkt_typ
        self.empfangene_anfragen: list[OrderAnfrage] = []

    def platziere_order(self, anfrage: OrderAnfrage) -> OrderBestaetigung:
        self.empfangene_anfragen.append(anfrage)
        return OrderBestaetigung(
            order_id=str(uuid.uuid4()),
            broker_endpunkt_typ=self._broker_endpunkt_typ,
            titel_id=anfrage.titel_id,
            richtung=anfrage.richtung,
            order_typ=anfrage.order_typ,
            groesse=anfrage.groesse,
            preis=anfrage.preis,
        )


# ---------------------------------------------------------------------------
# AC1 — Kauf UND Verkauf werden ausgeführt
# ---------------------------------------------------------------------------


def test_ac1_kauf_order_wird_auf_gemeinsames_dto_normalisiert() -> None:
    """@trace ausfuehrung-paper#AC1 — eine gebilligte Kauf-Order wird auf
    `OrderAnfrage` normalisiert (richtung="kauf", groesse aus der
    freigegebenen Gate-Grösse)."""
    anfrage = erstelle_order_anfrage_fuer_kauf(
        _kauf_order(),
        _gate_entscheid(freigegebene_groesse=Decimal("800")),
        asset_class_id=1,
        order_typ="limit",
        preis=Decimal("150"),
    )

    assert anfrage.titel_id == "AAPL"
    assert anfrage.asset_class_id == 1
    assert anfrage.richtung == "kauf"
    assert anfrage.groesse == Decimal("800")
    assert anfrage.order_typ == "limit"
    assert anfrage.preis == Decimal("150")


def test_ac1_blockierte_kauf_order_wird_nicht_ausgefuehrt() -> None:
    """@trace ausfuehrung-paper#AC1 — ein `"blockieren"`-Gate-Entscheid
    darf nicht in eine ausführbare `OrderAnfrage` übersetzt werden."""
    with pytest.raises(ValueError, match="blockier"):
        erstelle_order_anfrage_fuer_kauf(
            _kauf_order(),
            _gate_entscheid(entscheid="blockieren", freigegebene_groesse=Decimal("0")),
            asset_class_id=1,
            order_typ="market",
        )


def test_ac1_grossenlose_kauf_order_wird_nicht_ausgefuehrt() -> None:
    """@trace ausfuehrung-paper#AC1 — auch ein Nicht-`"blockieren"`-
    Entscheid mit `freigegebene_groesse <= 0` darf keine `OrderAnfrage`
    erzeugen (Konsistenz-Guard, kein sinnloser 0-Order-Versand)."""
    with pytest.raises(ValueError):
        erstelle_order_anfrage_fuer_kauf(
            _kauf_order(),
            _gate_entscheid(entscheid="durchwinken", freigegebene_groesse=Decimal("0")),
            asset_class_id=1,
            order_typ="market",
        )


def test_ac1_verkaufsauftrag_wird_auf_gemeinsames_dto_normalisiert() -> None:
    """@trace ausfuehrung-paper#AC1 — ein Verkaufsauftrag wird auf eine
    Liste von `OrderAnfrage` normalisiert (richtung="verkauf", groesse aus
    der einzigen Tranche) — hier eine 1-Element-Tranche, also eine
    1-Element-Liste."""
    anfragen = erstelle_order_anfrage_fuer_verkauf(
        _verkaufsauftrag(order_typ="limit", preis=Decimal("140")), asset_class_id=1
    )

    assert len(anfragen) == 1
    anfrage = anfragen[0]
    assert anfrage.titel_id == "AAPL"
    assert anfrage.richtung == "verkauf"
    assert anfrage.groesse == Decimal("10")
    assert anfrage.order_typ == "limit"
    assert anfrage.preis == Decimal("140")


def test_ac1_gestaffelter_verkauf_erzeugt_eine_orderanfrage_je_tranche() -> None:
    """@trace ausfuehrung-paper#AC1 — ein gestaffelter Verkaufsauftrag
    (`ausfuehrungsprofil="gestaffelt"`) mit N Tranchen erzeugt N
    `OrderAnfrage`n, deren Mengen-Summe die volle Zielmenge ergibt (Review-
    Fix: verhindert, dass die GESAMTE Position in EINER Order an den
    Broker geht und damit die Tranchierung aus S-042/S-055 unterlaufen
    wird)."""
    auftrag = Verkaufsauftrag(
        titel_id="AAPL",
        menge=Decimal("30"),
        tranchen=(Decimal("10"), Decimal("12"), Decimal("8")),
        order_typ="limit",
        preis=Decimal("140"),
        ausfuehrungsprofil="gestaffelt",
        tranchen_trigger=None,
    )

    anfragen = erstelle_order_anfrage_fuer_verkauf(auftrag, asset_class_id=1)

    assert len(anfragen) == 3
    assert [a.groesse for a in anfragen] == [Decimal("10"), Decimal("12"), Decimal("8")]
    assert sum((a.groesse for a in anfragen), Decimal("0")) == auftrag.menge
    assert all(a.titel_id == "AAPL" and a.richtung == "verkauf" for a in anfragen)
    assert all(a.order_typ == "limit" and a.preis == Decimal("140") for a in anfragen)


def test_ac1_kauf_und_verkauf_werden_beide_ueber_fuehre_order_aus_ausgefuehrt() -> None:
    """@trace ausfuehrung-paper#AC1 — beide Order-Quellen (Kauf, Verkauf)
    laufen durch denselben `fuehre_order_aus`-Aufruf zu einer
    `OrderBestaetigung`."""
    ibkr_port = _FakeBrokerPort(broker_endpunkt_typ="ibkr_paper")
    krypto_port = _FakeBrokerPort(broker_endpunkt_typ="krypto_sim_brokerless")

    kauf_anfrage = erstelle_order_anfrage_fuer_kauf(
        _kauf_order(), _gate_entscheid(), asset_class_id=1, order_typ="market"
    )
    (verkauf_anfrage,) = erstelle_order_anfrage_fuer_verkauf(_verkaufsauftrag(), asset_class_id=1)

    kauf_bestaetigung = fuehre_order_aus(
        kauf_anfrage, ibkr_paper_port=ibkr_port, krypto_sim_port=krypto_port
    )
    verkauf_bestaetigung = fuehre_order_aus(
        verkauf_anfrage, ibkr_paper_port=ibkr_port, krypto_sim_port=krypto_port
    )

    assert kauf_bestaetigung.richtung == "kauf"
    assert verkauf_bestaetigung.richtung == "verkauf"
    assert kauf_anfrage in ibkr_port.empfangene_anfragen
    assert verkauf_anfrage in ibkr_port.empfangene_anfragen


# ---------------------------------------------------------------------------
# AC4 — derselbe Order-Code-Pfad, unabhängig vom injizierten Port
# ---------------------------------------------------------------------------


def test_ac4_fuehre_order_aus_hat_keinen_modus_parameter() -> None:
    """@trace ausfuehrung-paper#AC4 — strukturell belegt: die Signatur von
    `fuehre_order_aus` enthält keinen `modus`/`echt`/`live`-Parameter, über
    den eine getrennte Order-Logik nach Modus verzweigen könnte."""
    parameter_namen = set(inspect.signature(fuehre_order_aus).parameters)
    verbotene_namen = {"modus", "echt", "live", "simuliert"}
    assert not (parameter_namen & verbotene_namen)


def test_ac4_gleicher_aufruf_mit_unterschiedlichen_ports_liefert_deren_ergebnis() -> None:
    """@trace ausfuehrung-paper#AC4 — derselbe `fuehre_order_aus`-Aufruf
    (identische `OrderAnfrage`, identische Order-Erstellungslogik) liefert
    je nach injiziertem `BrokerPort` ein unterschiedliches Ergebnis — der
    EINZIGE variable Punkt ist der injizierte Port, nicht eine
    Fallunterscheidung innerhalb von `fuehre_order_aus` selbst."""
    (anfrage,) = erstelle_order_anfrage_fuer_verkauf(_verkaufsauftrag(), asset_class_id=1)

    # Zwei strukturell unterschiedliche Fake-Ports (stehen stellvertretend
    # für eine künftige "echt"- vs. "simuliert"-Implementierung, AC4).
    port_a = _FakeBrokerPort(broker_endpunkt_typ="ibkr_paper")
    port_b = _FakeBrokerPort(broker_endpunkt_typ="ibkr_paper")

    bestaetigung_a = fuehre_order_aus(anfrage, ibkr_paper_port=port_a, krypto_sim_port=port_a)
    bestaetigung_b = fuehre_order_aus(anfrage, ibkr_paper_port=port_b, krypto_sim_port=port_b)

    assert port_a.empfangene_anfragen == [anfrage]
    assert port_b.empfangene_anfragen == [anfrage]
    assert bestaetigung_a.titel_id == bestaetigung_b.titel_id == anfrage.titel_id


# ---------------------------------------------------------------------------
# AC5 — Broker-Endpunkt-Routing (IBKR-Paper vs. brokerlose Krypto-Sim)
# ---------------------------------------------------------------------------


def test_ac5_nicht_krypto_routet_auf_ibkr_paper() -> None:
    """@trace ausfuehrung-paper#AC5 — Default-Konfiguration: Aktien
    (Anlageklasse 1) routen auf `"ibkr_paper"`."""
    assert bestimme_broker_endpunkt_typ(1) == "ibkr_paper"


def test_ac5_krypto_routet_brokerlos_auf_krypto_sim() -> None:
    """@trace ausfuehrung-paper#AC5 — Default-Konfiguration: Krypto
    (Anlageklasse 7) routet auf `"krypto_sim_brokerless"` (kein Broker
    angebunden, deckt A3)."""
    assert bestimme_broker_endpunkt_typ(7) == "krypto_sim_brokerless"


def test_ac5_routing_ist_konfigurierbar() -> None:
    """@trace ausfuehrung-paper#AC5 — die brokerlose Menge ist
    konfigurierbar (P6, keine hartkodierte Anlageklassen-Grenze): eine
    andere Anlageklasse kann als brokerlos konfiguriert werden, Krypto (7)
    fällt dann auf den Default-Endpunkt zurück."""
    konfiguration = BrokerRoutingKonfiguration(brokerlose_anlageklassen_ids=frozenset({3}))

    assert bestimme_broker_endpunkt_typ(3, konfiguration=konfiguration) == "krypto_sim_brokerless"
    assert bestimme_broker_endpunkt_typ(7, konfiguration=konfiguration) == "ibkr_paper"


def test_ac5_fuehre_order_aus_routet_krypto_order_an_krypto_sim_port() -> None:
    """@trace ausfuehrung-paper#AC5 — `fuehre_order_aus` wählt für eine
    Krypto-`OrderAnfrage` den `krypto_sim_port`, nicht den
    `ibkr_paper_port`."""
    ibkr_port = _FakeBrokerPort(broker_endpunkt_typ="ibkr_paper")
    krypto_port = _FakeBrokerPort(broker_endpunkt_typ="krypto_sim_brokerless")
    (anfrage,) = erstelle_order_anfrage_fuer_verkauf(_verkaufsauftrag(), asset_class_id=7)

    bestaetigung = fuehre_order_aus(anfrage, ibkr_paper_port=ibkr_port, krypto_sim_port=krypto_port)

    assert bestaetigung.broker_endpunkt_typ == "krypto_sim_brokerless"
    assert anfrage in krypto_port.empfangene_anfragen
    assert ibkr_port.empfangene_anfragen == []


# ---------------------------------------------------------------------------
# AC6 — alle 6 Order-Typen werden umgesetzt
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("order_typ", ["market", "limit", "stop", "stop_limit", "trailing", "twap"])
def test_ac6_alle_order_typen_durchlaufen_die_kauf_order_erstellung(
    order_typ: ExecutionOrderTyp,
) -> None:
    """@trace ausfuehrung-paper#AC6 — jeder der 6 AC6-Order-Typen (Market,
    Limit, Stop, Stop-Limit, Trailing, TWAP) wird unverändert in die
    `OrderAnfrage` übernommen."""
    anfrage = erstelle_order_anfrage_fuer_kauf(
        _kauf_order(), _gate_entscheid(), asset_class_id=1, order_typ=order_typ
    )
    assert anfrage.order_typ == order_typ


@pytest.mark.parametrize(
    ("sizing_order_typ", "erwarteter_execution_typ"),
    [("market", "market"), ("limit", "limit"), ("stop_market", "stop"), ("twap", "twap")],
)
def test_ac6_verkauf_order_typen_werden_korrekt_gemappt(
    sizing_order_typ: str, erwarteter_execution_typ: str
) -> None:
    """@trace ausfuehrung-paper#AC6 — die 4 vom Exit-Sizing erzeugbaren
    `sizing.OrderTyp`-Werte werden korrekt auf den vollen AC6-Wertebereich
    gemappt, insbesondere `stop_market -> stop`."""
    (anfrage,) = erstelle_order_anfrage_fuer_verkauf(
        _verkaufsauftrag(order_typ=sizing_order_typ), asset_class_id=1
    )
    assert anfrage.order_typ == erwarteter_execution_typ


# ---------------------------------------------------------------------------
# AC2/AC3 (S-047) — Modus-Auflösung (global + je Anlageklasse) + MVP-Sperre
# ---------------------------------------------------------------------------


def test_ac2_ohne_konfiguration_liefert_default_simuliert() -> None:
    """@trace ausfuehrung-paper#AC2 — ohne explizite Konfiguration greift
    der `ModusKonfiguration`-Default (`global_modus="simuliert"`)."""
    assert bestimme_wirksamen_modus(1) == "simuliert"


def test_ac2_ohne_override_faellt_anlageklasse_auf_global_zurueck() -> None:
    """@trace ausfuehrung-paper#AC2 — eine Anlageklasse ohne eigenen
    Eintrag in `modus_je_anlageklasse` übernimmt `global_modus`."""
    konfiguration = ModusKonfiguration(
        global_modus="simuliert", modus_je_anlageklasse={7: "simuliert"}
    )
    assert bestimme_wirksamen_modus(1, konfiguration=konfiguration) == "simuliert"


def test_ac2_anlageklassen_override_gewinnt_gegen_global() -> None:
    """@trace ausfuehrung-paper#AC2 — die spezifischste gesetzte Ebene
    (Anlageklassen-Override) gewinnt gegen `global_modus`, unabhängig von
    der Richtung: hier ist Global `"echt"`, Klasse 7 überschreibt auf
    `"simuliert"` (kein Fehler, da der WIRKSAME Modus simuliert bleibt)."""
    konfiguration = ModusKonfiguration(global_modus="echt", modus_je_anlageklasse={7: "simuliert"})
    assert bestimme_wirksamen_modus(7, konfiguration=konfiguration) == "simuliert"


def test_ac3_global_echt_ohne_override_wird_hart_gesperrt() -> None:
    """@trace ausfuehrung-paper#AC3 — `global_modus="echt"` ohne
    Anlageklassen-Override löst für jede Anlageklasse
    `LiveModusGesperrtError` aus (BR-019 "Live ist gesperrt", MVP-Sperre)."""
    konfiguration = ModusKonfiguration(global_modus="echt")
    with pytest.raises(LiveModusGesperrtError):
        bestimme_wirksamen_modus(1, konfiguration=konfiguration)


def test_ac3_anlageklassen_override_auf_echt_wird_hart_gesperrt() -> None:
    """@trace ausfuehrung-paper#AC3 — auch ein Anlageklassen-spezifisches
    `"echt"` (Global bleibt `"simuliert"`) wird geblockt, nicht still auf
    `"simuliert"` heruntergestuft."""
    konfiguration = ModusKonfiguration(global_modus="simuliert", modus_je_anlageklasse={1: "echt"})
    with pytest.raises(LiveModusGesperrtError):
        bestimme_wirksamen_modus(1, konfiguration=konfiguration)

    # Andere Anlageklassen ohne Override bleiben unbetroffen (fallen auf
    # global_modus="simuliert" zurück).
    assert bestimme_wirksamen_modus(2, konfiguration=konfiguration) == "simuliert"


def test_ac3_kein_bestaetigungs_parameter_in_modus_und_order_ausfuehrung() -> None:
    """@trace ausfuehrung-paper#AC3 — "voll autonom ... keine
    Bestätigungsabfrage vor der Order": weder `bestimme_wirksamen_modus`
    noch `fuehre_order_aus` (bereits AC4, S-046) besitzen einen
    Bestätigungs-/Freigabe-Parameter."""
    parameter_namen = set(inspect.signature(bestimme_wirksamen_modus).parameters)
    assert not parameter_namen & {"bestaetigung", "bestaetigt", "confirm", "freigabe"}

    parameter_namen = set(inspect.signature(fuehre_order_aus).parameters)
    assert not parameter_namen & {"bestaetigung", "bestaetigt", "confirm", "freigabe"}


# ---------------------------------------------------------------------------
# AC3 (Review-Fix) — Allowlist (fail-closed) statt Denylist (fail-open)
# ---------------------------------------------------------------------------


def test_ac3_allowlist_blockiert_auch_einen_fremdwert_ausserhalb_von_echt_simuliert() -> None:
    """@trace ausfuehrung-paper#AC3 — Review-Fix (Sicherheit): die Sperre
    ist eine ALLOWLIST (nur `"simuliert"` durchgelassen), keine Denylist
    (nur `"echt"` geblockt). Ein Fremdwert, der weder `"echt"` noch
    `"simuliert"` ist, wird ebenfalls hart geblockt — nicht unbemerkt
    durchgelassen. `Modus` ist ein `Literal["echt", "simuliert"]`; ein
    Fremdwert lässt sich nur über `model_construct` (Umgehung der
    pydantic-Validierung) konstruieren, simuliert hier eine fehlerhafte/
    kompromittierte Konfigurationsquelle."""
    konfiguration = ModusKonfiguration.model_construct(
        global_modus="paper_pro",  # type: ignore[arg-type]
        modus_je_anlageklasse=MappingProxyType({}),
    )

    with pytest.raises(LiveModusGesperrtError):
        bestimme_wirksamen_modus(1, konfiguration=konfiguration)


def test_ac3_allowlist_blockiert_fremdwert_als_anlageklassen_override() -> None:
    """@trace ausfuehrung-paper#AC3 — dieselbe Allowlist-Sperre greift
    auch, wenn der Fremdwert über `modus_je_anlageklasse` (statt
    `global_modus`) hereinkommt."""
    konfiguration = ModusKonfiguration.model_construct(
        global_modus="simuliert",
        modus_je_anlageklasse=MappingProxyType({1: "paper_pro"}),  # type: ignore[dict-item]
    )

    with pytest.raises(LiveModusGesperrtError):
        bestimme_wirksamen_modus(1, konfiguration=konfiguration)


# ---------------------------------------------------------------------------
# AC3 (Review-Fix) — aktive Verdrahtung in `fuehre_order_aus`
# ---------------------------------------------------------------------------


def test_ac3_fuehre_order_aus_blockiert_echt_modus_vor_dem_broker_aufruf() -> None:
    """@trace ausfuehrung-paper#AC3 — `fuehre_order_aus` löst den Modus
    für `anfrage.asset_class_id` auf und wirft `LiveModusGesperrtError`,
    BEVOR ein `BrokerPort` erreicht wird — kein Broker-Aufruf erfolgt bei
    gesperrtem Modus (Review-Fix: vorher hatte `bestimme_wirksamen_modus`
    keinen Aufrufer im Order-Pfad)."""
    ibkr_port = _FakeBrokerPort(broker_endpunkt_typ="ibkr_paper")
    krypto_port = _FakeBrokerPort(broker_endpunkt_typ="krypto_sim_brokerless")
    (anfrage,) = erstelle_order_anfrage_fuer_verkauf(_verkaufsauftrag(), asset_class_id=1)
    modus_konfiguration = ModusKonfiguration(global_modus="echt")

    with pytest.raises(LiveModusGesperrtError):
        fuehre_order_aus(
            anfrage,
            ibkr_paper_port=ibkr_port,
            krypto_sim_port=krypto_port,
            modus_konfiguration=modus_konfiguration,
        )

    assert ibkr_port.empfangene_anfragen == []
    assert krypto_port.empfangene_anfragen == []


def test_ac3_fuehre_order_aus_blockiert_anlageklassen_spezifisches_echt() -> None:
    """@trace ausfuehrung-paper#AC3 — die Sperre greift auch, wenn nur die
    konkrete `anfrage.asset_class_id` per Override auf `"echt"` gesetzt
    ist (Global bleibt `"simuliert"`)."""
    ibkr_port = _FakeBrokerPort(broker_endpunkt_typ="ibkr_paper")
    krypto_port = _FakeBrokerPort(broker_endpunkt_typ="krypto_sim_brokerless")
    (anfrage,) = erstelle_order_anfrage_fuer_verkauf(_verkaufsauftrag(), asset_class_id=1)
    modus_konfiguration = ModusKonfiguration(
        global_modus="simuliert", modus_je_anlageklasse={1: "echt"}
    )

    with pytest.raises(LiveModusGesperrtError):
        fuehre_order_aus(
            anfrage,
            ibkr_paper_port=ibkr_port,
            krypto_sim_port=krypto_port,
            modus_konfiguration=modus_konfiguration,
        )

    assert ibkr_port.empfangene_anfragen == []


def test_ac3_fuehre_order_aus_laesst_simulierten_modus_ohne_konfiguration_durch() -> None:
    """@trace ausfuehrung-paper#AC3 — ohne `modus_konfiguration` (Default
    `None` -> `ModusKonfiguration()`, `global_modus="simuliert"`) läuft
    `fuehre_order_aus` unverändert durch (kein Regressions-Bruch der
    bestehenden AC1/AC4/AC5-Tests, die `modus_konfiguration` nicht
    setzen)."""
    ibkr_port = _FakeBrokerPort(broker_endpunkt_typ="ibkr_paper")
    krypto_port = _FakeBrokerPort(broker_endpunkt_typ="krypto_sim_brokerless")
    (anfrage,) = erstelle_order_anfrage_fuer_verkauf(_verkaufsauftrag(), asset_class_id=1)

    bestaetigung = fuehre_order_aus(anfrage, ibkr_paper_port=ibkr_port, krypto_sim_port=krypto_port)

    assert bestaetigung.richtung == "verkauf"
    assert anfrage in ibkr_port.empfangene_anfragen
