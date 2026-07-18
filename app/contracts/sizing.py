"""Modul-Vertrag Position-Sizing-Kern (Story S-039, Spec
`docs/specs/sizing.md` AC1/AC2/AC3/AC4/AC7) + Exit-Sizing-Ausführung
(Story S-042, AC8/AC12) + Exit-Sizing-Feintuning (Story S-055,
AC9/AC10/AC11).

architecture.md §2 P2 ("Explizite Modul-Verträge"): jeder Modul-Übergang
läuft über ein typisiertes DTO in `app/contracts/`. Dieses Modul bildet den
**Kelly-Kern**-Ausschnitt des Verträge-Abschnitts "Konfiguration:
Kelly-Fraktion je Anlageklasse, Trade-Cap %, Trade-Minimum für
Kelly-Schärfung, ..." sowie einen Teil des "Position-Sizing Output"
(`eingesetzte_kelly_fraktion`, `risiko_pct`, `verworfen?`) ab.

`ordergroesse` (absolute Geldsumme) und `titel_id`-Pass-Through in den
vollen Output-Vertrag fehlen hier bewusst: sie setzen eine Kapitalbasis
und die Pre-Trade-Kostenkalkulation voraus (AC5/AC6 der Spec) — beides
ist NICHT Teil dieser Story ("Position-Sizing-Kern: Kelly-Formel,
Fraktionen, hartes Cap, Scharfschaltung", ohne Kosten-/Mindestgrössen-
Prüfung). Dieses Modul liefert ausschliesslich den **Risiko-Anteil des
Kapitals** (`risiko_pct`, 0–1) als Prozentsatz; `OrdergroessenKonfiguration`/
`OrdergroessenErgebnis` (Story S-041, unten) kombinieren das additiv mit
Kapitalbasis + Kosten zur absoluten `ordergroesse`.
"""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

#: AC2/C-006-Default: Anlageklassen-IDs, die als "volatil" gelten (Krypto = 7,
#: `docs/concept.md`). Bewusst als konfigurierbarer Default (nicht als
#: hartkodierte Code-Grenze im Domain-Kern) — architecture.md §2 P6:
#: "Anlageklassen sind Konfiguration, keine Code-Grenze; kein
#: `if asset_class == …` im Kern". Ein Aufrufer/Orchestrierungs-Layer kann die
#: Menge über `KellyFraktionsKonfiguration.volatile_anlageklassen_ids`
#: überschreiben (z.B. aus einer künftigen `AssetClass`-Konfig-Spalte gespeist).
DEFAULT_VOLATILE_ANLAGEKLASSEN_IDS: frozenset[int] = frozenset({7})


class KellyFraktionsKonfiguration(BaseModel):
    """AC2/AC3/AC4: die konfigurierbaren Sizing-Parameter (Verträge:
    "Kelly-Fraktion je Anlageklasse, Trade-Cap %, Trade-Minimum für
    Kelly-Schärfung") — alle Werte sind Defaults, provisorisch,
    konfigurierbar (Spec-Formulierung).

    `fraktion_volatil` ist zugleich die Obergrenze der für volatile
    Anlageklassen eingesetzten Fraktion (AC2: "Quarter-Kelly wirkt
    zugleich als Obergrenze der eingesetzten Fraktion") — ein Aufrufer
    kann diesen Wert nach unten konfigurieren, aber
    `bestimme_konfigurierte_fraktion` deckelt ihn zusätzlich hart auf
    `QUARTER_KELLY_OBERGRENZE`.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    #: AC2: Standard-Fraktion (Half-Kelly) für nicht-volatile Anlageklassen.
    fraktion_standard: Decimal = Field(default=Decimal("0.5"), gt=0)
    #: AC2: Fraktion für volatile Anlageklassen (z.B. Krypto, Quarter-Kelly).
    fraktion_volatil: Decimal = Field(default=Decimal("0.25"), gt=0)
    #: AC3: hartes Cap auf das Risiko je Trade (Spec-Bereich 1–2 %, als
    #: Anteil 0–1, nicht Prozentpunkte 0–100).
    trade_cap_pct: Decimal = Field(default=Decimal("0.02"), gt=0)
    #: AC4: Mindestzahl abgeschlossener Simulations-Trades, ab der Kelly
    #: "scharf" geschaltet wird (Spec-Bereich 50–100).
    kelly_min_trades: int = Field(default=100, ge=0)
    #: A2/AC4: konservative Fixed-Fractional-Ersatzgrösse, solange Kelly
    #: nicht scharf ist.
    fixed_fractional_pct: Decimal = Field(default=Decimal("0.01"), gt=0)
    #: AC2/P6: Anlageklassen-IDs, die als volatil gelten (Quarter-Kelly statt
    #: Half-Kelly). Konfigurierbar statt hartkodierte Code-Grenze im Kern
    #: (architecture.md §2 P6, C-006) — Default Krypto (7).
    volatile_anlageklassen_ids: frozenset[int] = Field(default=DEFAULT_VOLATILE_ANLAGEKLASSEN_IDS)


class PositionSizingErgebnis(BaseModel):
    """AC1/AC2/AC3/AC4-Ausschnitt des "Position-Sizing Output"-Vertrags:
    `{ titel_id, eingesetzte_kelly_fraktion, risiko_pct, verworfen? }`
    (ohne `ordergroesse`, siehe Moduldocstring).

    `eingesetzte_kelly_fraktion` ist die rohe Kelly-Fraktion `f*` (AC1),
    multipliziert mit der nach AC2 bestimmten Fraktion (Half-/Quarter-
    Kelly) — **vor** dem AC3-Cap; `None`, solange Kelly nicht scharf
    geschaltet ist (AC4, Fixed-Fractional-Rückfall greift, kein
    Kelly-Wert "eingesetzt").

    `risiko_pct` ist der **finale** eingesetzte Anteil des Kapitals (0–1)
    nach Anwendung des AC3-Hartcaps (gilt für beide Zweige — Kelly UND
    Fixed-Fractional, siehe `position_sizing`-Moduldocstring) — die Basis,
    aus der eine Folgestory zusammen mit einer Kapitalbasis + Kosten
    (AC5/AC6) die absolute `ordergroesse` bildet.

    `verworfen` trägt `"kelly-negativ"`, wenn `f*` ≤ 0 ist (AC1, deckt
    E1: "negatives Kelly → kein Trade") — in diesem Fall ist `risiko_pct`
    `0`.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    titel_id: str = Field(min_length=1)
    eingesetzte_kelly_fraktion: Decimal | None = None
    risiko_pct: Decimal = Field(ge=0)
    kelly_scharf: bool
    verworfen: str | None = None


class OrdergroessenKonfiguration(BaseModel):
    """AC6 (Story S-041): die konfigurierbare Mindest-Ordergrösse
    (Verträge: "Mindest-Ordergrösse" — "Default, provisorisch,
    konfigurierbar", Mindestgebühr-Effekt, deckt E2). Bewusst ein
    eigenständiges Modell statt einer Erweiterung von
    `KellyFraktionsKonfiguration` (S-039, additiv/unverändert)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    #: AC6: Mindest-Ordergrösse in CHF (Netto, nach Kostenabzug, AC5).
    #: Unterschreitet die geplante Ordergrösse diesen Wert, wird kein
    #: Auftrag erzeugt (Default provisorisch).
    mindest_ordergroesse_chf: Decimal = Field(default=Decimal("50"), gt=0)


class OrdergroessenErgebnis(BaseModel):
    """AC5/AC6-Ausschnitt (Story S-041) des "Position-Sizing Output"-
    Vertrags: `{ titel_id, ordergroesse, verworfen? }` — kombiniert
    `risiko_pct` (S-039, `PositionSizingErgebnis`) + Kapitalbasis +
    erwartete Kosten (S-017, `ErwarteteKosten`) zur absoluten
    Netto-Ordergrösse.

    `ordergroesse_chf` ist die finale, um die erwarteten Kosten (AC5)
    reduzierte Ordergrösse — `0`, sobald `verworfen` gesetzt ist.
    `ordergroesse_brutto_chf` ist die ungekürzte Grösse vor Kostenabzug
    (`risiko_pct * kapitalbasis_chf`), zu Nachvollziehbarkeitszwecken.

    `verworfen` trägt `"kosten-uebersteigen-ertrag"`, wenn nach
    Kostenabzug keine positive Netto-Grösse verbleibt (AC5, deckt E1-
    Analogon "kein positiver erwarteter Gewinn"), bzw.
    `"unter-mindest-ordergroesse"`, wenn die verbleibende Netto-Grösse
    die konfigurierte Mindest-Ordergrösse unterschreitet (AC6, deckt
    E2)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    titel_id: str = Field(min_length=1)
    ordergroesse_chf: Decimal = Field(ge=0)
    ordergroesse_brutto_chf: Decimal = Field(ge=0)
    kosten_chf: Decimal = Field(ge=0)
    verworfen: str | None = None


#: AC8 (Story S-042) + AC10 (Story S-055): der Wertebereich des
#: Verträge-Felds "Exit-Sizing Output ... order_typ:
#: market|stop_market|limit|twap". `"market"` bleibt Teil des vollen
#: Vertrags-Wertebereichs, wird aber von `app.domain.sizing.exit_sizing`
#: weiterhin nicht erzeugt (Hard-Exit liefert `"stop_market"`, nicht
#: `"market"` — Edge-Cases-Begründung "Fill sicher, Preis nicht"). `"twap"`
#: wird seit S-055 (AC10) für Soft-Exits erzeugt, deren Positionsgrösse
#: relativ zum Handelsvolumen die konfigurierte TWAP-Schwelle erreicht.
OrderTyp = Literal["market", "stop_market", "limit", "twap"]

#: AC8 (Story S-042): die zwei Ausführungsprofile eines Verkaufsauftrags —
#: "sofort" (Hard-Exit, "sofort die gesamte Position") vs. "gestaffelt"
#: (Soft-Exit).
Ausfuehrungsprofil = Literal["sofort", "gestaffelt"]

#: AC11 (Story S-055): der Wertebereich des Abstands-Auslösers zwischen
#: aufeinanderfolgenden Tranchen eines gestaffelten Exits — "zeitbasiert"
#: (fester Zeitabstand) oder "ereignisbasiert" (Spec-Wortlaut: "weitere
#: −X % oder weitere negative News").
TranchenAbstandsArt = Literal["zeitbasiert", "ereignisbasiert"]


class TranchenAbstandsTrigger(BaseModel):
    """AC11: beschreibt, wodurch der Abstand zwischen aufeinanderfolgenden
    Tranchen eines gestaffelten Exits ausgelöst wird — entweder
    zeitbasiert (`zeitabstand` zwischen zwei Tranchen) oder ereignisbasiert
    (`weitere_bewegung_pct`: eine weitere negative Kursbewegung um X % seit
    der letzten Tranche löst die nächste aus; "weitere negative News" ist
    als Ereignis-Trigger derselben `art` gedacht, aber nicht Teil dieses
    reinen Domain-Kerns — News-Erkennung kommt aus `[[analyse-pipelines]]`,
    nicht aus Exit-Sizing).

    Trägt jeweils nur das zur `art` passende Feld — das andere bleibt
    `None` (kein gemischter Trigger)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    art: TranchenAbstandsArt
    zeitabstand: timedelta | None = None
    weitere_bewegung_pct: Decimal | None = None


class ExitSizingKonfiguration(BaseModel):
    """AC9/AC10/AC11 (Story S-055): die konfigurierbaren Exit-Sizing-
    Feintuning-Parameter (Verträge: "Limit-Anteil-Ziel (Default 95 %),
    TWAP-Schwelle, Default-Tranchenzahl") — alle Werte sind Defaults,
    provisorisch, konfigurierbar (Spec-Formulierung, analog
    `KellyFraktionsKonfiguration`/`OrdergroessenKonfiguration`)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    #: AC9: Ziel-Anteil an Limit-Orders über alle Ausführungen (Spec: "≥
    #: 95 % Limit-Orders").
    limit_anteil_ziel: Decimal = Field(default=Decimal("0.95"), gt=0, le=1)
    #: AC10: Auslöse-Schwelle für TWAP als Positionsgrösse relativ zum
    #: Handelsvolumen (Anteil 0–1, z.B. 0.10 = 10 % des Tagesvolumens).
    twap_schwelle_pct: Decimal = Field(default=Decimal("0.10"), gt=0)
    #: AC11: Anzahl Tranchen eines gestaffelten Exits (Spec-Bereich 3–4).
    anzahl_tranchen: int = Field(default=3, ge=3, le=4)
    #: AC11: welche Art von Abstands-Auslöser zwischen den Tranchen gilt.
    tranchen_abstand_art: TranchenAbstandsArt = "zeitbasiert"
    #: AC11: Default-Zeitabstand zwischen zwei Tranchen, sofern
    #: `tranchen_abstand_art == "zeitbasiert"`.
    tranchen_zeitabstand: timedelta = Field(default=timedelta(days=1))
    #: AC11: Default-Schwelle für "weitere −X %"-Kursbewegung, sofern
    #: `tranchen_abstand_art == "ereignisbasiert"`.
    tranchen_weitere_bewegung_pct: Decimal = Field(default=Decimal("0.05"), gt=0)


class Verkaufsauftrag(BaseModel):
    """AC8/AC11/AC12-Vertrag "Exit-Sizing Output" (Story S-042, erweitert
    S-055): `{ titel_id, menge, tranchen[], order_typ, preis?,
    ausfuehrungsprofil }` — die direkte Übergabe von Exit-Sizing an das
    Kauf- & Verkaufsmodul (AC12, umgeht bewusst das Risikomanagement,
    siehe `app.domain.sizing.exit_sizing`-Moduldocstring).

    `menge` ist die volle Zielmenge des Verkaufs (die Entscheidung, WIE
    VIEL der Position verkauft wird, ist Teil der beim Kauf fixierten
    Exit-Regeln, → C-014, Nicht-Ziel dieser Spec); `tranchen` zerlegt
    diese Menge in einzelne Ausführungs-Teilmengen — bei Hard-Exit
    (`ausfuehrungsprofil="sofort"`) weiterhin ein Einzel-Element mit der
    vollen `menge` (AC8), bei Soft-Exit (`ausfuehrungsprofil="gestaffelt"`)
    seit S-055 die AC11-Zerlegung in 3–4 Teilmengen (Summe == `menge`,
    keine Rundungsverluste). `tranchen_trigger` (AC11) beschreibt, wodurch
    der Abstand zwischen den Tranchen ausgelöst wird — `None` bei
    Hard-Exit (Einzel-Tranche, kein Abstand). `preis` bleibt optional/
    `None`, solange keine Preisfindung Teil einer umgesetzten AC ist."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    titel_id: str = Field(min_length=1)
    menge: Decimal = Field(gt=0)
    tranchen: tuple[Decimal, ...] = Field(min_length=1)
    order_typ: OrderTyp
    preis: Decimal | None = None
    ausfuehrungsprofil: Ausfuehrungsprofil
    tranchen_trigger: TranchenAbstandsTrigger | None = None


class LimitAnteilKpi(BaseModel):
    """AC9-Vertrag: die messbare Betriebs-Kennzahl "Limit-Anteil" über
    eine Menge bereits erzeugter `Verkaufsauftrag`-Ausführungen (Spec: "über
    alle Ausführungen sollen ≥ 95 % Limit-Orders sein ... als messbare
    Betriebs-Kennzahl geführt").

    `limit_anteil` ist der Anteil (0–1) der Ausführungen mit
    `order_typ == "limit"` an `anzahl_gesamt`; bei `anzahl_gesamt == 0`
    (keine Ausführungen) gilt `limit_anteil == 1` und `ziel_erreicht ==
    True` (kein Datenpunkt verletzt das Ziel — vakuose Wahrheit)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    anzahl_gesamt: int = Field(ge=0)
    anzahl_limit: int = Field(ge=0)
    limit_anteil: Decimal = Field(ge=0, le=1)
    ziel: Decimal = Field(gt=0, le=1)
    ziel_erreicht: bool


__all__ = [
    "Ausfuehrungsprofil",
    "ExitSizingKonfiguration",
    "KellyFraktionsKonfiguration",
    "LimitAnteilKpi",
    "OrderTyp",
    "OrdergroessenErgebnis",
    "OrdergroessenKonfiguration",
    "PositionSizingErgebnis",
    "TranchenAbstandsArt",
    "TranchenAbstandsTrigger",
    "Verkaufsauftrag",
]
