"""Risikomanagement-Gate: Drei-Wege-Entscheid + volle Prüfmatrix
(Storys S-044 AC2/AC5/AC6/AC12 und S-045 AC8/AC9/AC10, Spec
`docs/specs/risikomanagement.md`, BR-014/BR-013/BR-138).

Reiner Domain-Kern (architecture.md §4 P1/P3): keine I/O, kein LLM, keine
DB, kein eigener Grenzwert (AC11 — Grenzwerte kommen ausschliesslich als
`DepotstrategieKonfiguration`-Parameter herein, erzeugt von
`app.db.depotstrategie.lade_aktive_depotstrategie()`, S-043). Deckt:

- **AC5** — "Das Risikomanagement-Gate greift nur beim Kauf; jeder
  Verkaufsauftrag umgeht das Gate vollständig und ungeprüft." Strukturell
  umgesetzt durch Unterlassung + Signatur (analog zu `app.domain.sizing
  .exit_sizing`, S-042/AC12 der `sizing.md`-Spec, BR-013): `pruefe_kauf_gate`
  nimmt ausschliesslich eine `AnnotierteKaufOrder` (Kauf-Attribut-Bündel,
  S-040) entgegen — es gibt in diesem Modul keinen Aufrufpfad, über den ein
  `Verkaufsauftrag` (`app.contracts.sizing`) das Gate durchläuft.
  `tests/architecture/test_gate_greift_nur_beim_kauf.py` belegt zusätzlich
  strukturell (AST-Scan, spiegelbildlich zu
  `test_exit_sizing_umgeht_risikomanagement.py`), dass der Verkaufs-Pfad
  (`app/domain/sizing/`) dieses Modul nicht importiert.
- **AC6** — `pruefe_kauf_gate` liefert je Aufruf genau einen von drei
  Entscheiden (`GateEntscheid.entscheid`): `"durchwinken"` (volle geplante
  Grösse), `"deckeln"` (Kappung auf das erlaubte Maximum — **kein**
  Rück-Durchlauf ins Position-Sizing, reine Kappung des bereits fixierten
  `AnnotierteKaufOrder.ordergroesse`-Werts) oder `"blockieren"`
  (`freigegebene_groesse=0`).
- **AC12** — kann kein `DepotStand` geladen werden (`depot_stand=None`,
  deckt E1), liefert das Gate `"blockieren"` — "das Gate trifft keinen
  Durchwink-Entscheid; der Kauf wird sicherheitshalber nicht freigegeben".
  Analog behandelt: keine aktive Depotstrategie (`depotstrategie=None`) —
  ohne Grenzwert kein Entscheid möglich (siehe `app.db.depotstrategie
  .lade_aktive_depotstrategie`-Docstring: "ein Gate-Konsument muss diesen
  Fall analog E1 der Spec behandeln").

**AC8 (Klumpenrisiko, S-045):** ergänzt die S-044-Sektor-/Branchen-Prüfung
(AC2) um zwei weitere Klumpen-Dimensionen — Anlageklasse (nur falls für die
Klasse des Kauf-Kandidaten ein `max_anlageklasse_pct`-Eintrag konfiguriert
ist, sonst "kein Limit konfiguriert", siehe `DepotstrategieKonfiguration`-
Docstring) und Einzelposition (alle bestehenden Lots **desselben Titels**,
wertgewichtet). Alle Prüfungen laufen über dieselbe generische
`_pruefe_gruppen_limit`-Formel (siehe dort).

**AC9 (Korrelations-/Cluster-Prüfung, S-045):** ein weiterer Titel eines
bereits stark vertretenen Korrelations-Clusters (`Instrument
.korrelations_cluster`, → BR-138) kann gedeckelt/blockiert werden, auch
wenn das nominelle Sektorlimit noch nicht erreicht ist — dieselbe
wertgewichtete Konzentrationsformel wie die Sektor-Prüfung (AC2), aber über
eine unabhängige Gruppierungsachse. Die Depotstrategie (AC1/AC11) sieht
keinen eigenen Korrelations-Limit-Wert vor; die Prüfung verwendet daher
`max_sektor_pct` als Grenzwert (AC11: "Gate ... definiert keine eigenen
Grenzwerte" — kein neues Feld erfunden). Edge-Case ("Korrelations-Daten
nicht verfügbar -> konservativ statt überspringen"): ein Kauf-Kandidat oder
eine bestehende Position ohne bekannten Cluster fällt in einen gemeinsamen
`UNBEKANNTER_CLUSTER`-Bucket (analog `UNBEKANNTE_BRANCHE`) statt aus der
Prüfung zu fallen — eine wachsende Konzentration unbekannter Cluster wird
so selbst zum Deckelungs-/Blockade-Treiber, statt die Prüfung stillschweigend
auszulassen. Eine echte Stress- vs. Normalphasen-Korrelationsmessung
(Datenquelle/Zeitfenster) ist laut Spec "Offene Punkte" weiterhin offen und
nicht Teil dieser Story — die konservative Behandlung fehlender/unbekannter
Cluster-Zuordnung ist die hier gebaute Operationalisierung des
Edge-Case-Wortlauts.

**AC10 (portfolio-weiter Kelly-Cap, S-045):** `gesamt_exposure_cap_pct`
begrenzt den wertgewichteten Anteil aller **Nicht-Cash**-Positionen
(`asset_class_id != CASH_ASSET_CLASS_ID`, Anlageklasse 3) am Gesamtdepot —
dieselbe Konzentrationsformel, Gruppierungsachse "Cash vs. Nicht-Cash".
Kauft der Kandidat selbst die Cash-Klasse (praktisch irrelevant für einen
Kauf-Order-Pfad), entfällt diese Prüfung (kein Exposure-Zuwachs).

**AC8-Checklisten-Eintrag "Drawdown-Limits":** die Spec nennt in AC8
"Drawdown-Limits" als eine von vier Prüfmatrix-Dimensionen, präzisiert dies
aber an keiner weiteren Stelle mit einem eigenen Grenzwert-Feld — im
Gegenteil: die Nicht-Ziele schliessen einen "Gesamt-Drawdown-Kill-Switch"
im Risikomanagement-Gate explizit aus ("die Kill-Switch-Schwelle ... gehört
in [[betriebssicherung]]"), und die "Offene Punkte" listen die
Gesamt-Drawdown-Kill-Switch-Schwelle ausdrücklich als dorthin verwiesen.
Diese Story implementiert daher KEINE eigene Drawdown-Schwelle im Gate
(das wäre entweder eine Duplikation von `app.core.drawdown_monitor`/
`kill_switch`, S-025, oder ein von AC11 nicht gedecktes neues
Depotstrategie-Feld) — siehe die entsprechende Präzisierung unter AC8 in
`docs/specs/risikomanagement.md`.

Edge-Case (Spec §Edge-Cases, nicht separat nummeriert, Teil der
AC6-Entscheidungslogik): eine geplante Ordergrösse `<= 0` führt ebenfalls
zu `"blockieren"` — es gibt nichts, das durchgewinkt oder gedeckelt werden
könnte.

`depot_stand`/`depotstrategie`/`gics_branche`/`asset_class_id`/
`korrelations_cluster` kommen als Parameter herein (P1, kein DB-Zugriff) —
ein künftiger Orchestrierungs-Layer speist sie aus `app.domain.portfolio
.portfolio_aggregate.ermittle_depot_stand`, `app.db.depotstrategie
.lade_aktive_depotstrategie` und den Instrument-Stammdaten
(`Instrument.gics_sector`/`Instrument.korrelations_cluster`,
`Instrument.asset_class_id`). Keines dieser Felder ist Teil von
`AnnotierteKaufOrder` (`docs/specs/strategie-exit-regeln.md` §Verträge
"Output" führt keines davon) — analog zu `PositionsBestand.gics_branche`
(S-036) werden sie hier separat übergeben.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

from app.contracts.risikomanagement import DepotstrategieKonfiguration, GateEntscheid
from app.contracts.strategie_exit_regeln import AnnotierteKaufOrder
from app.domain.portfolio.portfolio_aggregate import (
    CASH_ASSET_CLASS_ID,
    UNBEKANNTE_BRANCHE,
    DepotStand,
    positionswert,
)
from app.domain.portfolio.ports import PositionsBestand

#: Rundungsraster für CHF-Geldbeträge (NUMERIC(20,8)-kompatibel, P7/ADR-010)
#: — kaufmännisch gerundet (`ROUND_HALF_UP`), analog zu
#: `app.domain.portfolio.position_booking._quantize_geld`.
_GELD_QUANTUM = Decimal("0.00000001")

#: 100 % als Anteil (1.0) — Grenze, ab der ein Limit real keine Deckelung/
#: Blockade mehr bewirken kann (Division durch `1 - Anteil` in
#: `_max_erlaubte_zusatz_fuer_gruppe` wäre sonst durch 0).
_VOLLER_ANTEIL = Decimal("1")

#: Sentinel-Schlüssel für Positionen/Kauf-Kandidaten ohne bekannte
#: Korrelations-Cluster-Zuordnung (AC9-Edge-Case: "konservativ ... statt
#: die Korrelationsprüfung zu überspringen") — analog `UNBEKANNTE_BRANCHE`.
UNBEKANNTER_CLUSTER = "unbekannt"


def _quantize_geld(wert: Decimal) -> Decimal:
    return wert.quantize(_GELD_QUANTUM, rounding=ROUND_HALF_UP)


def _branche(gics_branche: str | None) -> str:
    """Sentinel-Behandlung analog `portfolio_aggregate.berechne_portfolio_
    aggregat` — fehlende Branchenzuordnung (`None`) fällt in den
    `UNBEKANNTE_BRANCHE`-Bucket statt aus der Prüfung zu fallen."""
    return gics_branche or UNBEKANNTE_BRANCHE


def _cluster(korrelations_cluster: str | None) -> str:
    """Sentinel-Behandlung analog `_branche` (AC9-Edge-Case, siehe
    Moduldocstring)."""
    return korrelations_cluster or UNBEKANNTER_CLUSTER


def _max_erlaubte_zusatz_fuer_gruppe(
    *, gruppenwert_bestehend: Decimal, gesamtwert_bestehend: Decimal, max_anteil: Decimal
) -> Decimal:
    """Löst `(gruppenwert_bestehend + x) / (gesamtwert_bestehend + x) ==
    max_anteil` nach `x` auf — die grösste zusätzliche Investition in
    dieser Gruppe (Sektor/Klasse/Einzelposition/Cluster/Nicht-Cash-
    Exposure), die das jeweilige Limit exakt trifft (AC2/AC8/AC9/AC10,
    A1, "Order genau am Limit -> gilt als eingehalten"). Voraussetzung:
    `max_anteil < 1` (sonst kein reales Limit, siehe Aufrufer). Das
    Ergebnis ist `<= 0`, sobald `gruppenwert_bestehend / gesamtwert_
    bestehend >= max_anteil` (Limit bereits ausgeschöpft) — dieser Fall
    muss vom Aufrufer NICHT separat behandelt werden, die Formel liefert
    ihn automatisch mit."""
    zaehler = max_anteil * gesamtwert_bestehend - gruppenwert_bestehend
    nenner = _VOLLER_ANTEIL - max_anteil
    return zaehler / nenner


@dataclass(frozen=True)
class _GruppenPruefung:
    """Ergebnis einer einzelnen Konzentrations-Prüfung (eine von
    Sektor/Klasse/Einzelposition/Cluster/Exposure): `max_erlaubte_zusatz`
    ist die grösste zusätzliche Investition, die dieses eine Limit noch
    zulässt — `None`, wenn für diese Gruppe kein reales Limit greift
    (Limit >= 100 % oder gar nicht konfiguriert, z.B. keine
    `max_anlageklasse_pct`-Eintrag für die betroffene Klasse)."""

    label: str
    max_erlaubte_zusatz: Decimal | None


def _pruefe_gruppen_limit(
    *,
    label: str,
    gruppenwert_bestehend: Decimal,
    gesamtwert_bestehend: Decimal,
    max_anteil: Decimal | None,
) -> _GruppenPruefung:
    if max_anteil is None or max_anteil >= _VOLLER_ANTEIL:
        return _GruppenPruefung(label=label, max_erlaubte_zusatz=None)
    return _GruppenPruefung(
        label=label,
        max_erlaubte_zusatz=_max_erlaubte_zusatz_fuer_gruppe(
            gruppenwert_bestehend=gruppenwert_bestehend,
            gesamtwert_bestehend=gesamtwert_bestehend,
            max_anteil=max_anteil,
        ),
    )


def _wert_je_gruppe(positionen: tuple[PositionsBestand, ...], zugehoerig) -> Decimal:
    """Summiert `positionswert` über alle Positionen, für die `zugehoerig`
    wahr ist (wertgewichtet, AC2/AC8/AC9/AC10 — "über alle Positionen
    hinweg, nicht die nominelle Anzahl Titel")."""
    return sum((positionswert(p) for p in positionen if zugehoerig(p)), Decimal("0"))


def pruefe_kauf_gate(
    kauf_order: AnnotierteKaufOrder,
    *,
    gics_branche: str | None,
    asset_class_id: int,
    korrelations_cluster: str | None = None,
    depotstrategie: DepotstrategieKonfiguration | None,
    depot_stand: DepotStand | None,
) -> GateEntscheid:
    """AC2/AC6/AC8/AC9/AC10/AC12: prüft `kauf_order` gegen die volle
    Prüfmatrix (Sektor/Klasse/Einzelposition/Korrelations-Cluster/
    portfolio-weites Exposure) der aktiven Depotstrategie und trifft den
    Drei-Wege-Entscheid.

    Args:
        kauf_order: das fixierte Attribut-Bündel (S-040) — nur
            Kauf-Orders (AC5, siehe Moduldocstring).
        gics_branche: GICS-Branche des Kauf-Kandidaten (`Instrument
            .gics_sector`, `None` falls nicht gepflegt — fällt dann in den
            `UNBEKANNTE_BRANCHE`-Bucket, siehe `_branche`).
        asset_class_id: Anlageklasse des Kauf-Kandidaten (`Instrument
            .asset_class_id`) — Grundlage der Klassen- (AC8) und
            Kelly-Cap-Prüfung (AC10).
        korrelations_cluster: Korrelations-Cluster des Kauf-Kandidaten
            (`Instrument.korrelations_cluster`, → BR-138), `None` falls
            nicht gepflegt — fällt dann in den `UNBEKANNTER_CLUSTER`-Bucket
            (AC9-Edge-Case, siehe `_cluster`). Default `None`, da noch
            keine Story die Erst-Befüllung dieser Spalte besitzt (siehe
            `app.db.models.Instrument`-Docstring).
        depotstrategie: die aktuell aktive Depotstrategie-Konfiguration
            (`app.db.depotstrategie.lade_aktive_depotstrategie`, AC11) —
            `None`, wenn keine Depotstrategie aktiv ist (kein Grenzwert
            verfügbar).
        depot_stand: der aktuelle Depot-Stand (`app.domain.portfolio
            .portfolio_aggregate.ermittle_depot_stand`) — `None`, wenn er
            nicht geladen werden konnte (AC12, E1).

    Returns:
        `GateEntscheid` mit genau einem der drei Entscheide (AC6).
    """
    if depot_stand is None:
        return GateEntscheid(
            entscheid="blockieren",
            freigegebene_groesse=_quantize_geld(Decimal("0")),
            begruendung=(
                "Depot-Stand konnte nicht geladen werden (E1) — der Kauf wird "
                "sicherheitshalber nicht freigegeben (AC12)."
            ),
        )

    if depotstrategie is None:
        return GateEntscheid(
            entscheid="blockieren",
            freigegebene_groesse=_quantize_geld(Decimal("0")),
            begruendung=(
                "Keine aktive Depotstrategie konfiguriert — kein Grenzwert "
                "verfügbar, der Kauf wird analog E1 nicht freigegeben (AC11, "
                "app.db.depotstrategie.lade_aktive_depotstrategie)."
            ),
        )

    if kauf_order.ordergroesse <= 0:
        return GateEntscheid(
            entscheid="blockieren",
            freigegebene_groesse=_quantize_geld(Decimal("0")),
            begruendung=(
                f"Geplante Ordergrösse {kauf_order.ordergroesse!r} ist <= 0 — "
                "keine Freigabe (Edge-Case §Edge-Cases & Fehlerverhalten)."
            ),
        )

    branche = _branche(gics_branche)
    cluster = _cluster(korrelations_cluster)
    positionen = depot_stand.positionen
    gesamtwert_bestehend = sum((positionswert(p) for p in positionen), Decimal("0"))

    if gesamtwert_bestehend == 0:
        # Cold-Start: leeres (aber erfolgreich geladenes) Depot — es gibt noch
        # keine bestehende Konzentration in IRGENDEINER geprüften Dimension
        # (Sektor/Klasse/Einzelposition/Cluster/Exposure), gegen die der
        # allererste Kauf verstossen könnte (AC2/AC8/AC9/AC10). Die
        # Gewichtung einer einzelnen ersten Position ist in jeder dieser
        # Dimensionen rechnerisch immer 100 % des Depots, das ist aber KEIN
        # Konzentrations-RISIKO im Sinne dieser Prüfmatrix (Diversifikation
        # baut sich erst über weitere Käufe auf). Ohne diesen Sonderfall
        # würde JEDE der fünf Formeln jede erste Order auf 100% werfen und
        # permanent blockieren (coder-Lesson S-044, dieselbe Klasse Fehler
        # für jede neue x/(x+bestehend)-Formel).
        return GateEntscheid(
            entscheid="durchwinken",
            freigegebene_groesse=_quantize_geld(kauf_order.ordergroesse),
            begruendung=(
                f"Erster Kauf in ein leeres Depot (Branche {branche!r}, Klasse "
                f"{asset_class_id}, Cluster {cluster!r}) — keine bestehende "
                "Konzentration in irgendeiner geprüften Dimension, volle Grösse "
                "freigegeben (AC2/AC6/AC8/AC9/AC10)."
            ),
        )

    sektorwert_bestehend = _wert_je_gruppe(
        positionen, lambda p: _branche(p.gics_branche) == branche
    )
    einzelpositionswert_bestehend = _wert_je_gruppe(
        positionen, lambda p: p.titel_id == kauf_order.titel_id
    )
    clusterwert_bestehend = _wert_je_gruppe(
        positionen, lambda p: _cluster(p.korrelations_cluster) == cluster
    )
    exposure_wert_bestehend = _wert_je_gruppe(
        positionen, lambda p: p.asset_class_id != CASH_ASSET_CLASS_ID
    )

    pruefungen = [
        _pruefe_gruppen_limit(
            label=f"Sektor {branche!r}",
            gruppenwert_bestehend=sektorwert_bestehend,
            gesamtwert_bestehend=gesamtwert_bestehend,
            max_anteil=depotstrategie.max_sektor_pct / 100,
        ),
        _pruefe_gruppen_limit(
            label=f"Einzelposition {kauf_order.titel_id!r}",
            gruppenwert_bestehend=einzelpositionswert_bestehend,
            gesamtwert_bestehend=gesamtwert_bestehend,
            max_anteil=depotstrategie.max_einzelposition_pct / 100,
        ),
        _pruefe_gruppen_limit(
            label=f"Korrelations-Cluster {cluster!r}",
            gruppenwert_bestehend=clusterwert_bestehend,
            gesamtwert_bestehend=gesamtwert_bestehend,
            # AC9: kein eigenes Depotstrategie-Feld (AC11) — Wiederverwendung
            # des Sektor-Limits als konservativer Grenzwert für die zweite
            # Gruppierungsachse (siehe Moduldocstring).
            max_anteil=depotstrategie.max_sektor_pct / 100,
        ),
    ]

    klassen_limit_pct = depotstrategie.max_anlageklasse_pct.get(asset_class_id)
    klassenwert_bestehend = _wert_je_gruppe(
        positionen, lambda p: p.asset_class_id == asset_class_id
    )
    pruefungen.append(
        _pruefe_gruppen_limit(
            label=f"Anlageklasse {asset_class_id}",
            gruppenwert_bestehend=klassenwert_bestehend,
            gesamtwert_bestehend=gesamtwert_bestehend,
            # Fehlender Eintrag = "kein Klassen-Limit konfiguriert" (siehe
            # DepotstrategieKonfiguration-Docstring), NICHT "Limit 0".
            max_anteil=klassen_limit_pct / 100 if klassen_limit_pct is not None else None,
        )
    )

    if asset_class_id != CASH_ASSET_CLASS_ID:
        pruefungen.append(
            _pruefe_gruppen_limit(
                label="Portfolio-weites Exposure (Kelly-Cap)",
                gruppenwert_bestehend=exposure_wert_bestehend,
                gesamtwert_bestehend=gesamtwert_bestehend,
                max_anteil=depotstrategie.gesamt_exposure_cap_pct / 100,
            )
        )

    bindende_pruefungen = [p for p in pruefungen if p.max_erlaubte_zusatz is not None]

    if not bindende_pruefungen:
        return GateEntscheid(
            entscheid="durchwinken",
            freigegebene_groesse=_quantize_geld(kauf_order.ordergroesse),
            begruendung=("Kein in der Prüfmatrix reales Limit greift — volle Grösse freigegeben."),
        )

    bindend = min(bindende_pruefungen, key=lambda p: p.max_erlaubte_zusatz)

    if bindend.max_erlaubte_zusatz <= 0:
        return GateEntscheid(
            entscheid="blockieren",
            freigegebene_groesse=_quantize_geld(Decimal("0")),
            begruendung=(
                f"Limit für {bindend.label} bereits ausgeschöpft — Kauf wird "
                "blockiert (AC2/AC8/AC9/AC10, A2)."
            ),
        )

    if kauf_order.ordergroesse <= bindend.max_erlaubte_zusatz:
        return GateEntscheid(
            entscheid="durchwinken",
            freigegebene_groesse=_quantize_geld(kauf_order.ordergroesse),
            begruendung="Alle geprüften Limits eingehalten — volle Grösse freigegeben.",
        )

    return GateEntscheid(
        entscheid="deckeln",
        freigegebene_groesse=_quantize_geld(bindend.max_erlaubte_zusatz),
        begruendung=(
            f"Volle Grösse würde das Limit für {bindend.label} überschreiten — "
            f"Order auf {_quantize_geld(bindend.max_erlaubte_zusatz)} CHF gedeckelt, "
            "kein Rück-Durchlauf ins Position-Sizing (AC6/A1)."
        ),
    )


__all__ = ["pruefe_kauf_gate", "UNBEKANNTER_CLUSTER"]
