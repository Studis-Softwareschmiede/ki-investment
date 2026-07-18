"""Modul-Verträge Handelsplattform-Stammdaten & erwartete Kosten (Story
S-017, Spec `docs/specs/ausfuehrung-paper.md` AC10/AC11) + Order-
Ausführungs-Kern (Story S-046, AC1/AC4/AC5/AC6).

architecture.md §2 P2 ("Explizite Modul-Verträge"): jeder Modul-Übergang
läuft über ein typisiertes DTO. Dieses Modul bildet den Verträge-Abschnitt
"Handelsplattform-Stammdaten (Referenzdaten): je Plattform/Anlageklasse
`{ gebuehrenmodell, mindestgebuehr, typischer_spread }` → erwartete Kosten
an Position-/Exit-Sizing" ab, soweit diese Story (AC10, AC11) ihn betrifft:

- `PlattformStammdaten` — die AC10-Referenzdaten EINER Plattform/Anlageklasse-
  Kombination (`{ gebuehrenmodell, mindestgebuehr, typischer_spread }`),
  ergaenzt um die Plattform-Identität für den Konsumenten.
- `ErwarteteKosten` — der AC11-Vertrag "erwartete Kosten (Courtage + Spread +
  geschätzte Slippage) an die Sizing-Module (Pre-Trade-Kalkulation)", inkl.
  des Edge-Case-Flags `mindestgebuehr_greift` ("Order kleiner als die
  Mindest-Ordergrösse/Mindestgebühr-Schwelle → das Modul meldet dies zurück
  (Mindestgebühr-Effekt), statt einen unwirtschaftlichen Trade auszuführen" —
  die eigentliche Entscheidung "Trade trotzdem ausführen oder verwerfen"
  liegt beim (künftigen) Sizing-Modul-Konsumenten, Nicht-Ziel dieser Story).

Die Position-/Exit-Sizing-Module selbst existieren in dieser Codebasis noch
nicht (Cold-Start, spätere Story) — `app.db.trading_platform` ist der
erzeugende Endpunkt dieser Verträge, kein Konsument ist Teil dieser Story.

**S-046 ergänzt** (`app.domain.execution.order_ausfuehrung`, siehe dortiger
Moduldocstring für die vollständige AC1/AC4/AC5/AC6-Herleitung):

- `ExecutionOrderTyp` — die vollen AC6-Order-Typen (Market, Limit, Stop,
  Stop-Limit, Trailing, TWAP), die der Order-Ausführungs-Kern "umsetzt".
- `OrderRichtung` — kauf | verkauf (AC1: das Modul führt beide aus).
- `BrokerEndpunktTyp` + `BrokerRoutingKonfiguration` — die AC5-Auswahl
  zwischen IBKR-Paper (Broker angebunden) und brokerloser Krypto-Simulation
  (kein Broker angebunden), analog dem P6-Konfigurationsmuster
  `app.contracts.sizing.KellyFraktionsKonfiguration
  .volatile_anlageklassen_ids` (Anlageklassen sind Konfiguration, keine
  Code-Grenze).
- `OrderAnfrage` — die vereinheitlichte Order-Anfrage, auf die sowohl Kauf-
  als auch Verkaufs-Eingaben normalisiert werden, BEVOR sie den
  gemeinsamen Order-Code-Pfad durchlaufen (AC4: "derselbe Order-Code-Pfad
  ... nicht in getrennter Order-Logik").
- `OrderBestaetigung` — die minimale Bestätigung eines Broker-Ports, dass
  eine `OrderAnfrage` angenommen wurde. Bewusst OHNE Fill-/Reject-/
  Timeout-Status (AC7/AC8, eigene Folge-Story S-048) und ohne Slippage-
  /Spread-Simulation (AC9, S-049) — dieser Vertrag deckt nur die
  Order-ANNAHME durch den gewählten Endpunkt.

**S-047 ergänzt** (`app.domain.execution.order_ausfuehrung
.bestimme_wirksamen_modus`, AC2/AC3, BR-019):

- `ModusKonfiguration` — der AC2-Modus-Schalter «echt/simuliert»: global
  gesetzt, je Anlageklasse überschreibbar (Spec A1: "der wirksame Modus
  je Order ergibt sich aus der spezifischsten gesetzten Ebene"). Analoges
  Konfigurationsmuster zu `BrokerRoutingKonfiguration` (global + je-
  Anlageklasse-Override statt hartkodierter Code-Grenze, architecture.md
  §2 P6). Lässt strukturell `"echt"` zu (forward-kompatibel für eine
  spätere Live-Freischaltung) — die tatsächliche MVP-Sperre (AC3,
  BR-019 "Live ist gesperrt", Nicht-Ziel "Kein Live-/Echtgeld-Handel im
  MVP") erzwingt ausschliesslich `bestimme_wirksamen_modus` selbst, nicht
  dieser Kontrakt.
"""

from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.contracts.depot import Modus


class PlattformStammdaten(BaseModel):
    """AC10-Referenzdaten EINER Plattform/Anlageklasse-Kombination:
    `{ gebuehrenmodell, mindestgebuehr, typischer_spread }`, ergaenzt um die
    Plattform-/Anlageklassen-Identität."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    plattform_id: uuid.UUID
    plattform_name: str = Field(min_length=1)
    asset_class_id: int = Field(ge=1, le=11)
    gebuehrenmodell: str | None = None
    mindestgebuehr_chf: Decimal
    typischer_spread_pct: Decimal | None = None


class ErwarteteKosten(BaseModel):
    """AC11-Vertrag: erwartete Kosten (Courtage + Spread + geschätzte
    Slippage) an die Sizing-Module (Pre-Trade-Kalkulation).

    `courtage_chf` ist die reine Prozent-Berechnung (`order_wert_chf *
    courtage_pct`), `courtage_effektiv_chf` bereits mit der
    Mindestgebühr-Untergrenze verrechnet (`max(courtage_chf,
    mindestgebuehr_chf)`) — `mindestgebuehr_greift=True` markiert den
    Edge-Case, in dem die Mindestgebühr die eigentliche Prozent-Courtage
    übersteigt (Verträge/Edge-Cases: "Mindestgebühr-Effekt").
    `gesamtkosten_chf` ist die Summe aus `courtage_effektiv_chf`,
    `spread_kosten_chf` und `geschaetzte_slippage_chf`."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    plattform_id: uuid.UUID
    plattform_name: str = Field(min_length=1)
    asset_class_id: int = Field(ge=1, le=11)
    order_wert_chf: Decimal = Field(gt=0)
    courtage_chf: Decimal
    mindestgebuehr_chf: Decimal
    courtage_effektiv_chf: Decimal
    mindestgebuehr_greift: bool
    spread_kosten_chf: Decimal
    geschaetzte_slippage_chf: Decimal
    gesamtkosten_chf: Decimal


#: AC6 (S-046): der volle Order-Typ-Wertebereich, den der Order-
#: Ausführungs-Kern "umsetzt" (Spec-Wortlaut: "Market, Limit, Stop,
#: Stop-Limit, Trailing und TWAP"). Bewusst EIGENSTÄNDIG neben
#: `app.contracts.sizing.OrderTyp` (4 Werte, `market|stop_market|limit|
#: twap`) statt dessen Erweiterung: `sizing.OrderTyp` ist der Vertrag EINES
#: bereits gebauten Erzeugers (Exit-Sizing, S-042/S-055) mit eigenem,
#: engerem Wertebereich — dieser Order-Typ hier ist der VOLLE, vom
#: Order-Ausführungs-Kern zu handhabende Bereich (Verkaufsaufträge werden
#: über `_VERKAUF_ORDER_TYP_MAP` hineingemappt, `stop_market -> stop`,
#: siehe `app.domain.execution.order_ausfuehrung`-Moduldocstring). Analog
#: zu `Verkaufsauftrag.order_typ`, dessen `"market"`-Wert laut eigenem
#: Docstring ebenfalls "Teil des vollen Vertrags-Wertebereichs" ist, ohne
#: dass der aktuelle Erzeuger ihn je liefert.
ExecutionOrderTyp = Literal["market", "limit", "stop", "stop_limit", "trailing", "twap"]

#: AC1 (S-046): die Order-Richtung — deckt "sowohl Käufe ... als auch
#: Verkäufe" ab.
OrderRichtung = Literal["kauf", "verkauf"]

#: AC5 (S-046): die beiden MVP-Broker-Endpunkt-Typen — IBKR im Paper-Modus
#: (Default, Broker angebunden) bzw. brokerlose Krypto-Simulation (kein
#: Broker angebunden, deckt A3). Weitere Broker (Live, ein zweiter
#: Krypto-Broker à la Kraken, → "Offene Punkte") sind Nicht-Ziel des MVP.
BrokerEndpunktTyp = Literal["ibkr_paper", "krypto_sim_brokerless"]

#: AC5-Default: Anlageklassen-IDs ohne angebundenen Broker (Krypto = 7,
#: `docs/concept.md`, analog `app.contracts.sizing
#: .DEFAULT_VOLATILE_ANLAGEKLASSEN_IDS`). Bewusst konfigurierbarer Default
#: statt hartkodierter Code-Grenze (architecture.md §2 P6).
DEFAULT_BROKERLOSE_ANLAGEKLASSEN_IDS: frozenset[int] = frozenset({7})


class BrokerRoutingKonfiguration(BaseModel):
    """AC5: die konfigurierbare Zuordnung "welche Anlageklassen haben
    keinen angebundenen Broker" (Verträge/Edge-Cases: "Ist für Krypto kein
    Broker angebunden, wird die Order im Paper-Modus brokerlos
    simuliert") — ein Aufrufer kann die Menge überschreiben (z.B. sobald
    ein künftiger Krypto-Broker angebunden ist, → "Offene Punkte:
    Krypto-Anbindung ... offen")."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    brokerlose_anlageklassen_ids: frozenset[int] = Field(
        default=DEFAULT_BROKERLOSE_ANLAGEKLASSEN_IDS
    )


class ModusKonfiguration(BaseModel):
    """AC2 (S-047): der Modus-Schalter «echt/simuliert» — global gesetzt,
    je Anlageklasse überschreibbar (Spec A1, BR-019: "global und je Klasse
    überschreibbar"). `modus_je_anlageklasse` trägt NUR die Anlageklassen
    mit einem expliziten Override; alle übrigen Anlageklassen fallen auf
    `global_modus` zurück — die Auflösung der "spezifischsten gesetzten
    Ebene" übernimmt
    `app.domain.execution.order_ausfuehrung.bestimme_wirksamen_modus`
    (dort auch die AC3/BR-019-MVP-Sperre gegen `"echt"`, NICHT hier: dieser
    Kontrakt bleibt bewusst forward-kompatibel für eine spätere
    Live-Freischaltung, siehe Moduldocstring)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    global_modus: Modus = "simuliert"
    modus_je_anlageklasse: dict[int, Modus] = Field(default_factory=dict)


class OrderAnfrage(BaseModel):
    """AC1/AC4: die vereinheitlichte Order-Anfrage — Kauf- UND
    Verkaufs-Eingaben werden auf DIESES EINE DTO normalisiert
    (`app.domain.execution.order_ausfuehrung
    .erstelle_order_anfrage_fuer_kauf`/`_fuer_verkauf`), bevor sie den
    gemeinsamen Order-Code-Pfad (`fuehre_order_aus`) durchlaufen — der
    Unterschied zwischen den beiden Modi «echt»/«simuliert» (AC4) liegt
    ausschliesslich darin, WELCHER `BrokerPort` injiziert wird, nicht in
    einer Fallunterscheidung innerhalb dieses Codepfads.

    `groesse` trägt die von der jeweiligen Quelle bereits fixierte
    Ordergrösse — bei `richtung="kauf"` ein CHF-Betrag
    (`GateEntscheid.freigegebene_groesse`, Position-Sizing-Kette), bei
    `richtung="verkauf"` eine Stückzahl (`Verkaufsauftrag.menge`,
    Exit-Sizing). Die Umrechnung CHF-Betrag → Stückzahl (setzt einen
    Fill-/Marktpreis voraus, der vor einer Market-Order-Ausführung gar
    nicht bekannt ist) ist NICHT Teil dieser Story — die vorgelagerten
    Sizing-Module liefern für Käufe bewusst nur einen Geldbetrag (siehe
    `app.contracts.sizing.OrdergroessenErgebnis`-Docstring), keine
    Stückzahl."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    titel_id: str = Field(min_length=1)
    asset_class_id: int = Field(ge=1, le=11)
    richtung: OrderRichtung
    groesse: Decimal = Field(gt=0)
    order_typ: ExecutionOrderTyp
    preis: Decimal | None = None


class OrderBestaetigung(BaseModel):
    """AC1/AC5: die Bestätigung eines `BrokerPort`, dass eine
    `OrderAnfrage` am gewählten Endpunkt angenommen wurde — echofasst die
    Anfrage plus den tatsächlich gewählten `broker_endpunkt_typ` (AC5-
    Beleg) und eine broker-seitig vergebene `order_id`.

    Bewusst OHNE Fill-Status (`gefuellt|teilfill|reject|timeout`, AC7/AC8
    — eigene Folge-Story S-048) und ohne Slippage-/Spread-Simulation
    (AC9 — S-049): dieses DTO deckt ausschliesslich die Order-ANNAHME."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    order_id: str = Field(min_length=1)
    broker_endpunkt_typ: BrokerEndpunktTyp
    titel_id: str = Field(min_length=1)
    richtung: OrderRichtung
    order_typ: ExecutionOrderTyp
    groesse: Decimal = Field(gt=0)
    preis: Decimal | None = None
