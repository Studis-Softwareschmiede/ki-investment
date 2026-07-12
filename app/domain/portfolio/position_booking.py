"""G/V-Rechnung, Gebühren-Netting & Einstand-Methode (Modul 16 Depotmodul,
Spec `docs/specs/depot.md`, Story S-016, AC2/AC3/AC5).

Setzt die eigentliche **Positions-Fortschreibung** um, die
`app.domain.portfolio.fill_booking.pruefe_fill` (S-015) bewusst ausgespart
hat: `verbuche_fill()` nimmt einen bereits über `pruefe_fill` als
`status == "gebucht"` geprüften `FillInput` entgegen und schreibt ihn gegen
den Positions-Bestand fort (via `PositionRepository`, P1 — kein
SQLAlchemy-Import hier).

- **AC2** — `berechne_unrealisierten_gv` / `berechne_realisierten_gv` sind
  die reinen Formel-Bausteine je Position; `aggregiere_gv` summiert über
  mehrere Positionen (Beide "je Position und aggregiert abrufbar").
- **AC3** — Gebühren-Netting: `_netter_kaufpreis` erhöht die Kostenbasis
  beim Kauf um die Kosten, `berechne_erloes_bei_verkauf` mindert den Erlös
  beim Verkauf um die Kosten — beide Pfade fliessen direkt in die G/V-
  Formeln ein (kein separater "Gebühren"-Posten, der vergessen werden
  könnte).
- **AC5** — Einstand-Methode konfigurierbar: bei `gleitender_durchschnitt`
  bleibt je Titel genau EIN offener Lot bestehen, dessen Ø-Einstandspreis
  sich bei einem Teilverkauf NICHT ändert (A1); bei `fifo` legt jeder Kauf
  einen neuen Lot an, ein Verkauf verbraucht die offenen Lots ältestenfalls
  zuerst (A2) — der Ø-Einstandspreis der (aus mehreren Lots bestehenden)
  Restposition kann sich dadurch effektiv ändern, weil unterschiedliche
  Lots unterschiedliche Einstandspreise tragen.

**Nicht Teil dieser Story** (siehe `docs/specs/depot.md`, andere Storys):
FX-Attribution (AC6 → S-053), Portfolio-Aggregate (AC8/AC9 → S-036). Der
unrealisierte G/V wird hier nur als **reine Formel** angeboten (AC2) — das
Nachführen des `unrealisierter_gv`-Spaltenwerts anhand des Live-Kurses
(Bewertungsfrequenz, Socket-Live-Kurs-Zugriff) ist eine eigene
Bewertungs-Schleife, kein Fill-getriebener Schreibpfad, und daher hier
NICHT verdrahtet.

**S-035 (AC4/AC7)** ergänzt: `verbuche_fill` schreibt nach jeder
erfolgreichen Buchung (Kauf ODER Verkauf, aber NICHT bei
`bereits_verbucht=True`, siehe unten) über `repository.schreibe_transaktion`
einen unveränderlichen Eintrag in die append-only Transaktionshistorie —
Arrival-Price + die daraus berechnete Slippage speichert der Repository-
Adapter (`app.domain.portfolio.transaction_historie.berechne_slippage`).
Bei einem Verkauf, der (FIFO, A2) mehrere Lots verbraucht, ist der Fill
keinem einzelnen Lot eindeutig zuordenbar — `position_id` wird in diesem
Fall `None` übergeben (siehe `_position_id_fuer_historie`).

**DBA-Zweit-Review (Iteration 2)** behebt drei Befunde:

- **Critical — Idempotenz (ADR-011/P8).** `verbuche_fill` prüft/markiert
  `fill.client_order_id` über `repository.markiere_fill_verbucht` als
  ALLERERSTE Aktion, bevor irgendeine Positions-Mutation stattfindet. Ist
  der Wert bereits bekannt (At-least-once-Zustellung hat denselben Fill
  doppelt zugestellt), bricht die Funktion ohne jede weitere Mutation ab
  und liefert `BuchungsErgebnis(bereits_verbucht=True)`.
- **Important — Lost-Update/TOCTOU + nicht gedeckter Verkauf.**
  `repository.offene_positionen` liest jetzt gesperrt (siehe
  `app.adapters.repositories.position_repository`); zusätzlich prüft
  `_verbuche_verkauf` VOR jeder Mutation, ob die Summe der verfügbaren
  Lot-Mengen die Verkaufsmenge deckt — reicht sie nicht (z. B. weil eine
  parallele Buchung zwischen `pruefe_fill`-Gate und diesem Aufruf Bestand
  entzogen hat), wird `UnzureichenderBestandFehler` geworfen (AC10-konform:
  nicht buchen, Bestand unverändert) STATT den Rest still fallen zu lassen.
- **Important — Rundungsdrift bei FIFO-Multi-Lot-Kostenverteilung.**
  `_verbuche_verkauf` verteilt `fill.kosten` nicht mehr rein proportional
  je Lot (das summiert bei nicht glatt teilbaren Mengen nicht exakt auf),
  sondern per Restbetrag-Buchführung: der zuletzt verbrauchte Lot erhält
  `fill.kosten − Σ bisheriger kosten_anteil`, wodurch die Summe über alle
  Lots exakt `fill.kosten` ergibt (P7/ADR-010: keine Float-artige
  Rundungslücke in Decimal-Arithmetik).

**DBA-Re-Review (Iteration 3, Important)** behebt einen weiteren Befund:

- **Mode-Isolation (BR-113/BR-130).** `_verbuche_kauf`/`_verbuche_verkauf`
  rufen `repository.offene_positionen` jetzt mit `mode=fill.mode` auf —
  ein „echt"-Fill mittelt/verbraucht ausschliesslich „echt"-Lots desselben
  Titels, ein „simuliert"-Fill ausschliesslich „simuliert"-Lots. Vorher
  filterte der Port nur nach `titel_id` + `status`, wodurch ein „echt"-Fill
  theoretisch gegen einen „simuliert"-Lot desselben Titels gemittelt oder
  verrechnet werden konnte (Verstoss gegen „echt/simuliert nie vermischt",
  BR-130).
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from typing import Literal

from app.contracts.depot import FillInput
from app.domain.portfolio.ports import OffenePosition, PositionRepository

EinstandMethode = Literal["gleitender_durchschnitt", "fifo"]

#: Rundungsraster an der Schreibgrenze (P7/ADR-010) — deckt sich mit dem
#: DB-Spaltentyp `NUMERIC(20,8)` (data-model.md §4 `position`/`transaction`).
_GELD_QUANTUM = Decimal("0.00000001")


def _quantize_geld(wert: Decimal) -> Decimal:
    """Rundet einen Geldwert an der Schreibgrenze auf 8 Nachkommastellen
    (NUMERIC(20,8), P7) — kaufmännisch gerundet (`ROUND_HALF_UP`), damit die
    Rundung nicht systematisch nach unten verzerrt."""
    return wert.quantize(_GELD_QUANTUM, rounding=ROUND_HALF_UP)


class UnzureichenderBestandFehler(ValueError):
    """Ein Verkauf(-santeil) übersteigt die Summe der verfügbaren offenen
    Lot-Mengen (DBA-Zweit-Review S-016, Important-Befund: Lost-Update/
    TOCTOU-Guard) — AC10-konform wird NICHT gebucht; der Aufrufer trägt die
    Verantwortung, dies als fehlerhaft zu protokollieren (analog zur
    bestehenden `ValueError` für „Unbekannte Strategie" in
    `SqlAlchemyPositionRepository.lege_position_an`)."""


@dataclass(frozen=True)
class LotBuchung:
    """Ein einzelner, gegen einen Lot verbuchter Anteil eines Verkaufs-Fills
    (AC2/AC3/AC5) — für FIFO typischerweise mehrere je Verkauf, für
    gleitenden Durchschnitt immer genau einer."""

    position_id: str
    verbrauchte_menge: Decimal
    resultierende_menge: Decimal
    realisierter_gv: Decimal


@dataclass(frozen=True)
class BuchungsErgebnis:
    """Ergebnis von `verbuche_fill()` — bei Kauf die (neu angelegte oder
    aktualisierte) Position, bei Verkauf die je Lot verbrauchten Anteile
    plus der aggregierte realisierte G/V (AC2, "aggregiert abrufbar").

    `bereits_verbucht=True` (DBA-Zweit-Review S-016, ADR-011) heisst: der
    `client_order_id`-Wert des Fills war bereits bekannt (At-least-once-
    Zustellung hat denselben Fill doppelt zugestellt) — es fand KEINE
    Mutation statt, alle anderen Felder bleiben auf ihrem Default."""

    richtung: Literal["kauf", "verkauf"]
    position_id: str | None = None
    lot_buchungen: tuple[LotBuchung, ...] = ()
    realisierter_gv_gesamt: Decimal = Decimal("0")
    bereits_verbucht: bool = False


def berechne_unrealisierten_gv(
    aktueller_preis: Decimal, einstand_preis: Decimal, menge: Decimal
) -> Decimal:
    """AC2: unrealisierter G/V je offener Position =
    `(aktueller Preis − Ø-Einstandspreis) × gehaltene Menge`."""
    return (aktueller_preis - einstand_preis) * menge


def berechne_realisierten_gv(
    erloes_netto: Decimal, einstand_preis: Decimal, verkaufte_menge: Decimal
) -> Decimal:
    """AC2/AC3: realisierter G/V je Verkauf(-santeil) = bereits
    gebühren-genetteter Erlös (`erloes_netto`, siehe
    `berechne_erloes_bei_verkauf`) abzüglich der Kostenbasis
    (`einstand_preis × verkaufte_menge`) — äquivalent zu
    `(Verkaufspreis − Ø-Einstandspreis) × verkaufte Menge`, wenn die Kosten
    bereits im Verkaufspreis genettet wurden."""
    return erloes_netto - (einstand_preis * verkaufte_menge)


def aggregiere_gv(werte: Iterable[Decimal]) -> Decimal:
    """AC2: aggregiert mehrere je-Position ermittelte G/V-Werte
    (realisiert oder unrealisiert) zu einer Summe."""
    return sum(werte, Decimal("0"))


def _netter_kaufpreis(kauf_menge: Decimal, kauf_preis: Decimal, kosten: Decimal) -> Decimal:
    """AC3: nettet die Kosten in die Kostenbasis EINES Kaufs — Basis für
    den (ggf. gewichteten) neuen Ø-Einstandspreis."""
    return (kauf_menge * kauf_preis + kosten) / kauf_menge


def berechne_neuen_einstand_bei_kauf(
    *,
    bisherige_menge: Decimal,
    bisheriger_einstand_preis: Decimal,
    kauf_menge: Decimal,
    kauf_preis: Decimal,
    kosten: Decimal,
) -> Decimal:
    """AC3/AC5 (gleitender Durchschnitt): neuer Ø-Einstandspreis nach einem
    Nachkauf — gewichteter Durchschnitt aus bisheriger Kostenbasis und der
    (gebühren-genetteten, AC3) Kostenbasis des neuen Kaufs. Bei
    `bisherige_menge == 0` (erster Kauf) ist das Ergebnis identisch zu
    `_netter_kaufpreis` allein."""
    bisherige_kostenbasis = bisherige_menge * bisheriger_einstand_preis
    neue_kostenbasis = kauf_menge * kauf_preis + kosten
    return (bisherige_kostenbasis + neue_kostenbasis) / (bisherige_menge + kauf_menge)


def berechne_erloes_bei_verkauf(
    verkauf_menge: Decimal, verkauf_preis: Decimal, kosten: Decimal
) -> Decimal:
    """AC3: nettet die (anteiligen) Kosten aus dem Bruttoerlös eines
    Verkaufs(-anteils) heraus — mindert den Erlös, statt ihn separat
    auszuweisen."""
    return verkauf_menge * verkauf_preis - kosten


def verbuche_fill(
    fill: FillInput, *, repository: PositionRepository, einstand_methode_default: EinstandMethode
) -> BuchungsErgebnis:
    """Schreibt einen bereits über `pruefe_fill` (S-015) als "gebucht"
    geprüften Fill gegen den Positions-Bestand fort (AC2/AC3/AC5). Bucht
    **nichts** doppelt und prüft keine Pflichtfelder/negative Menge erneut
    — das ist Aufgabe von `pruefe_fill`, deren Ergebnis Voraussetzung für
    den Aufruf dieser Funktion ist.

    ADR-011/P8 (DBA-Zweit-Review S-016, Critical-Befund): bevor irgendeine
    Positions-Mutation angestossen wird, markiert diese Funktion
    `fill.client_order_id` als verbucht. War der Wert bereits bekannt (die
    Redis-Queue lieferte denselben Fill ein zweites Mal), bricht die
    Funktion sofort ab — der Bestand bleibt unverändert.

    **Transaktionale Invariante (für den künftigen Aufrufer/Orchestrator):**
    Der Dedup-Marker wird NICHT separat committet, sondern nur geflusht —
    er wird erst durch denselben Commit durabel, der auch die
    Positions-Mutation(en) übernimmt. Wirft diese Funktion (oder eine der
    beiden Teilfunktionen) eine Exception (`UnzureichenderBestandFehler`,
    oder die bestehende `ValueError` für „Unbekannte Strategie"), MUSS der
    Aufrufer die GESAMTE Transaktion zurückrollen (nicht nur fangen und
    weitermachen) — sonst bliebe der Dedup-Marker fälschlich als „verbucht"
    stehen, obwohl der Fill nie tatsächlich gegen den Bestand fortgeschrieben
    wurde, und ein legitimer Retry desselben `client_order_id` würde später
    stillschweigend als Duplikat übersprungen."""
    ist_neuer_fill = repository.markiere_fill_verbucht(
        fill.client_order_id, titel_id=fill.titel_id, richtung=fill.richtung
    )
    if not ist_neuer_fill:
        return BuchungsErgebnis(richtung=fill.richtung, bereits_verbucht=True)

    if fill.richtung == "kauf":
        ergebnis = _verbuche_kauf(
            fill, repository=repository, einstand_methode_default=einstand_methode_default
        )
    else:
        ergebnis = _verbuche_verkauf(fill, repository=repository)

    # AC4/AC7 (S-035): append-only Transaktionshistorie-Eintrag NACH der
    # eigentlichen Positions-Buchung — derselbe Commit wie Dedup-Marker +
    # Positions-Mutation (siehe Transaktionale-Invariante oben).
    repository.schreibe_transaktion(fill, position_id=_position_id_fuer_historie(ergebnis))
    return ergebnis


def _position_id_fuer_historie(ergebnis: BuchungsErgebnis) -> str | None:
    """AC4/AC7 (S-035): welche `position_id` bekommt der
    Transaktionshistorie-Eintrag? Bei Kauf eindeutig die (neu angelegte
    oder aktualisierte) Position. Bei Verkauf nur dann eindeutig, wenn
    GENAU EIN Lot verbraucht wurde (gleitender Durchschnitt: immer; FIFO:
    nur falls der älteste Lot allein die Verkaufsmenge deckt) — verbraucht
    ein FIFO-Verkauf (A2) mehrere Lots, ist der Fill keinem einzelnen Lot
    eindeutig zuordenbar, daher `None` (der Verträge-Vertrag der Historie
    selbst referenziert ohnehin nur `titel_id`, keine `position_id`)."""
    if ergebnis.richtung == "kauf":
        return ergebnis.position_id
    if len(ergebnis.lot_buchungen) == 1:
        return ergebnis.lot_buchungen[0].position_id
    return None


def _verbuche_kauf(
    fill: FillInput, *, repository: PositionRepository, einstand_methode_default: EinstandMethode
) -> BuchungsErgebnis:
    offene_lots: list[OffenePosition] = repository.offene_positionen(fill.titel_id, mode=fill.mode)
    methode: EinstandMethode = (
        offene_lots[0].einstand_methode if offene_lots else einstand_methode_default  # type: ignore[assignment]
    )

    if methode == "fifo":
        neuer_einstand = _quantize_geld(_netter_kaufpreis(fill.menge, fill.fill_preis, fill.kosten))
        position_id = repository.lege_position_an(
            fill, einstand_preis=neuer_einstand, einstand_methode="fifo"
        )
        return BuchungsErgebnis(richtung="kauf", position_id=position_id)

    if not offene_lots:
        neuer_einstand = _quantize_geld(_netter_kaufpreis(fill.menge, fill.fill_preis, fill.kosten))
        position_id = repository.lege_position_an(
            fill, einstand_preis=neuer_einstand, einstand_methode="gleitender_durchschnitt"
        )
        return BuchungsErgebnis(richtung="kauf", position_id=position_id)

    lot = offene_lots[0]
    neuer_einstand = _quantize_geld(
        berechne_neuen_einstand_bei_kauf(
            bisherige_menge=lot.menge,
            bisheriger_einstand_preis=lot.einstand_preis,
            kauf_menge=fill.menge,
            kauf_preis=fill.fill_preis,
            kosten=fill.kosten,
        )
    )
    repository.aktualisiere_kauf(
        lot.position_id, neue_menge=lot.menge + fill.menge, neuer_einstand_preis=neuer_einstand
    )
    return BuchungsErgebnis(richtung="kauf", position_id=lot.position_id)


def _verbuche_verkauf(fill: FillInput, *, repository: PositionRepository) -> BuchungsErgebnis:
    offene_lots: list[OffenePosition] = repository.offene_positionen(fill.titel_id, mode=fill.mode)

    verfuegbare_menge = sum((lot.menge for lot in offene_lots), Decimal("0"))
    if fill.menge > verfuegbare_menge:
        # Important (DBA-Zweit-Review S-016): Lost-Update/TOCTOU-Guard —
        # trotz `offene_positionen`-Sperre und der vorgelagerten `pruefe_fill`-
        # Prüfung (S-015) kann sich der Bestand zwischen Gate und dieser
        # Buchung geändert haben (z. B. ein zwischenzeitlich verbuchter
        # zweiter Verkauf). AC10: nicht buchen, Bestand unverändert — statt
        # den nicht deckbaren Rest still fallen zu lassen.
        raise UnzureichenderBestandFehler(
            f"Verkauf von {fill.menge} ({fill.titel_id!r}) übersteigt den verfügbaren "
            f"Bestand ({verfuegbare_menge}) — Fill nicht gebucht (AC10)."
        )

    verbleibende_verkaufsmenge = fill.menge
    kosten_bereits_verteilt = Decimal("0")
    lot_buchungen: list[LotBuchung] = []

    for lot in offene_lots:
        if verbleibende_verkaufsmenge <= 0:
            break

        verbrauch = min(lot.menge, verbleibende_verkaufsmenge)
        if verbrauch <= 0:
            continue

        ist_letzter_verbrauch = verbrauch == verbleibende_verkaufsmenge
        if ist_letzter_verbrauch:
            # Important (DBA-Zweit-Review S-016): Restbetrag-Buchführung
            # statt rein anteiliger Kostenverteilung — der zuletzt
            # verbrauchte Lot erhält den vollen Rest, damit die Summe über
            # alle Lots exakt `fill.kosten` ergibt (keine Rundungsdrift bei
            # nicht glatt teilbaren Verkaufsmengen über mehrere Lots).
            kosten_anteil = fill.kosten - kosten_bereits_verteilt
        else:
            kosten_anteil = _quantize_geld(fill.kosten * (verbrauch / fill.menge))
        kosten_bereits_verteilt += kosten_anteil

        erloes_anteil = berechne_erloes_bei_verkauf(verbrauch, fill.fill_preis, kosten_anteil)
        realisierter_gv_anteil = _quantize_geld(
            berechne_realisierten_gv(erloes_anteil, lot.einstand_preis, verbrauch)
        )
        resultierende_menge = lot.menge - verbrauch

        repository.verbuche_verkauf_lot(
            lot.position_id,
            neue_menge=resultierende_menge,
            realisierter_gv_delta=realisierter_gv_anteil,
        )
        lot_buchungen.append(
            LotBuchung(
                position_id=lot.position_id,
                verbrauchte_menge=verbrauch,
                resultierende_menge=resultierende_menge,
                realisierter_gv=realisierter_gv_anteil,
            )
        )
        verbleibende_verkaufsmenge -= verbrauch

    return BuchungsErgebnis(
        richtung="verkauf",
        lot_buchungen=tuple(lot_buchungen),
        realisierter_gv_gesamt=aggregiere_gv(b.realisierter_gv for b in lot_buchungen),
    )
