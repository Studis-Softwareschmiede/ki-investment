"""FX-Attribution: Kapital- vs. Währungsgewinn in CHF-Basiswährung (Modul 16
Depotmodul, Spec `docs/specs/depot.md`, Story S-053, AC6, deckt A3).

Für Positionen/Trades in Fremdwährung (`waehrung != "CHF"`, C-002
Basiswährung) zerlegt dieses Modul den Gewinn/Verlust in zwei additive
Komponenten, beide bereits in CHF ausgewiesen:

- **Kapitalgewinn** (`kapital_gv_chf`) — die reine Kursbewegung des Titels
  in seiner Handelswährung, umgerechnet zum **Einstands-FX-Kurs** (so viel
  wäre der G/V in CHF, hätte sich der Wechselkurs seit dem Einstand nicht
  bewegt).
- **Währungsgewinn** (`waehrungs_gv_chf`) — der Effekt der
  Wechselkursbewegung selbst (Einstands- vs. aktueller/Verkaufs-FX-Kurs),
  angewandt auf den in Fremdwährung bereits realisierten/aktuellen
  Gegenwert.

Beide Formeln sind so konstruiert, dass ihre Summe exakt dem
gesamten G/V in CHF entspricht (kein unattribuierter Rest):

- Realisiert: `kapital_gv_chf + waehrungs_gv_chf == erloes_netto_chf −
  kostenbasis_chf` (= `erloes_netto × verkauf_fx_rate − einstand_preis ×
  menge × einstand_fx_rate`).
- Unrealisiert: `kapital_gv_chf + waehrungs_gv_chf == aktueller_preis ×
  menge × aktueller_fx_rate − einstand_preis × menge × einstand_fx_rate`.

Reine Formel-Bausteine (P1: kein DB-/Repository-Zugriff hier) — bewusst
**ohne** Import aus `app.domain.portfolio.position_booking` (obwohl die
realisierte Erlös-/G-V-Formel dort inhaltlich existiert), um keinen
Import-Zyklus zu erzeugen: `app.domain.portfolio.ports` importiert
`FxSplit` aus diesem Modul für die `PositionRepository`-Vertragstypisierung,
`position_booking` importiert wiederum `ports` — ein Import dieses Moduls
aus `position_booking` zurück in `ports`/`fx_attribution` bliebe zyklenfrei,
ein Import in die andere Richtung (hier → `position_booking`) nicht.

**Einstands-FX-Kurs bei Nachkauf (gleitender Durchschnitt, AC5-Analogie):**
`berechne_neuen_einstand_fx_rate_bei_kauf` mittelt den FX-Kurs nach exakt
demselben Muster wie `position_booking.berechne_neuen_einstand_bei_kauf`
den Ø-Einstandspreis mittelt — mengen-gewichteter Durchschnitt aus
bisherigem und neuem FX-Kurs. Bei FIFO ist keine Mittelung nötig (jeder
Kauf legt ohnehin einen eigenen Lot mit eigenem FX-Kurs an, analog zu
`einstand_preis`).

**Nicht Teil dieser Story:** das Nachführen von `Position.fx_kapital_gv`/
`fx_waehrungs_gv` (unrealisiert) über eine Live-Bewertungsschleife — analog
zu `unrealisierter_gv` (S-016) ist dies eine eigene, noch nicht gebaute
Bewertungs-Schleife (Socket-Live-Kurs-Zugriff für Instrument- **und**
FX-Kurs), kein Fill-getriebener Schreibpfad. Diese Datei liefert dafür nur
die reine Formel (`berechne_fx_split_unrealisiert`); wo der aktuelle
Instrument- bzw. FX-Kurs herkommt, ist Sache der künftigen
Bewertungsschleife-Story."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

#: Rundungsraster an der Schreibgrenze (P7/ADR-010) — deckt sich mit dem
#: DB-Spaltentyp `NUMERIC(20,8)` (data-model.md §4 `position`/`transaction`),
#: identische Konvention zu `position_booking._quantize_geld`.
_GELD_QUANTUM = Decimal("0.00000001")


def _quantize_geld(wert: Decimal) -> Decimal:
    """Rundet einen Geldwert an der Schreibgrenze auf 8 Nachkommastellen
    (NUMERIC(20,8), P7) — kaufmännisch gerundet (`ROUND_HALF_UP`)."""
    return wert.quantize(_GELD_QUANTUM, rounding=ROUND_HALF_UP)


@dataclass(frozen=True)
class FxSplit:
    """AC6: die beiden CHF-Komponenten der FX-Attribution — Kapital- und
    Währungsgewinn/-verlust. Ihre Summe entspricht exakt dem gesamten G/V
    in CHF (siehe Moduldocstring für den Nachweis je Formel)."""

    kapital_gv_chf: Decimal
    waehrungs_gv_chf: Decimal


def berechne_neuen_einstand_fx_rate_bei_kauf(
    *,
    bisherige_menge: Decimal,
    bisheriger_fx_rate: Decimal | None,
    kauf_menge: Decimal,
    kauf_fx_rate: Decimal,
) -> Decimal:
    """AC6/AC5-Analogie: neuer Ø-Einstands-FX-Kurs nach einem Nachkauf
    (gleitender Durchschnitt) — mengen-gewichteter Durchschnitt aus
    bisherigem und neuem FX-Kurs, identisches Muster zu
    `position_booking.berechne_neuen_einstand_bei_kauf`. Bei
    `bisherige_menge == 0` (erster Kauf) ist das Ergebnis `kauf_fx_rate`
    allein. Fehlt `bisheriger_fx_rate` ausnahmsweise (z. B. eine
    Bestandszeile ohne FX-Historie), wird defensiv `kauf_fx_rate` als
    alleinige Grundlage übernommen, statt mit `None` zu rechnen — dieser
    Fall ist bei konsistenter Handelswährung je Instrument nicht zu
    erwarten (jedes Instrument trägt genau eine `currency`, C-006)."""
    if bisherige_menge == 0 or bisheriger_fx_rate is None:
        return kauf_fx_rate
    bisherige_basis = bisherige_menge * bisheriger_fx_rate
    neue_basis = kauf_menge * kauf_fx_rate
    return (bisherige_basis + neue_basis) / (bisherige_menge + kauf_menge)


def berechne_fx_split_realisiert(
    *,
    einstand_preis: Decimal,
    einstand_fx_rate: Decimal,
    verkauf_preis: Decimal,
    verkauf_fx_rate: Decimal,
    verkaufte_menge: Decimal,
    kosten: Decimal,
) -> FxSplit:
    """AC6 (realisiert, deckt A3): zerlegt den realisierten G/V eines
    Verkaufs(-anteils) in Kapital- und Währungsgewinn, beide in CHF.

    - `kapital_gv_chf` = (gebühren-genetteter, lokaler) realisierter G/V
      (siehe `position_booking.berechne_realisierten_gv`) × Einstands-FX-
      Kurs — die reine Kursbewegung, bewertet zum FX-Kurs bei Einstand.
    - `waehrungs_gv_chf` = gebühren-genetteter Bruttoerlös ×
      (Verkaufs-FX-Kurs − Einstands-FX-Kurs) — der FX-Bewegungseffekt auf
      den tatsächlichen Erlös.

    Summe = `erloes_netto × verkauf_fx_rate − einstand_preis ×
    verkaufte_menge × einstand_fx_rate` (siehe Moduldocstring)."""
    erloes_netto = verkaufte_menge * verkauf_preis - kosten
    gv_lokal = erloes_netto - einstand_preis * verkaufte_menge
    kapital_gv_chf = _quantize_geld(gv_lokal * einstand_fx_rate)
    waehrungs_gv_chf = _quantize_geld(erloes_netto * (verkauf_fx_rate - einstand_fx_rate))
    return FxSplit(kapital_gv_chf=kapital_gv_chf, waehrungs_gv_chf=waehrungs_gv_chf)


def berechne_fx_split_unrealisiert(
    *,
    aktueller_preis: Decimal,
    einstand_preis: Decimal,
    aktueller_fx_rate: Decimal,
    einstand_fx_rate: Decimal,
    menge: Decimal,
) -> FxSplit:
    """AC6 (unrealisiert, deckt A3): zerlegt den unrealisierten G/V einer
    offenen Fremdwährungsposition in Kapital- und Währungsgewinn, beide in
    CHF — reine Formel, analog zu `position_booking
    .berechne_unrealisierten_gv`, hier um die FX-Komponente erweitert.

    - `kapital_gv_chf` = (aktueller Preis − Ø-Einstandspreis) × Menge ×
      Einstands-FX-Kurs.
    - `waehrungs_gv_chf` = aktueller Preis × Menge × (aktueller FX-Kurs −
      Einstands-FX-Kurs).

    Summe = `aktueller_preis × menge × aktueller_fx_rate − einstand_preis ×
    menge × einstand_fx_rate` (siehe Moduldocstring). **Nicht** an einen
    Schreibpfad angebunden (siehe Moduldocstring: Bewertungsschleife ist
    eigene, noch nicht gebaute Story)."""
    kapital_gv_chf = _quantize_geld((aktueller_preis - einstand_preis) * menge * einstand_fx_rate)
    waehrungs_gv_chf = _quantize_geld(
        aktueller_preis * menge * (aktueller_fx_rate - einstand_fx_rate)
    )
    return FxSplit(kapital_gv_chf=kapital_gv_chf, waehrungs_gv_chf=waehrungs_gv_chf)


def aggregiere_fx_split(werte: Iterable[FxSplit]) -> FxSplit:
    """AC6: aggregiert mehrere je-Lot ermittelte FX-Splits (z. B. ein
    FIFO-Verkauf über mehrere unterschiedlich bepreiste/FX-datierte Lots,
    A2) zu einem Gesamt-Split — gleiche Summen-Konvention wie
    `position_booking.aggregiere_gv`."""
    kapital_gesamt = Decimal("0")
    waehrung_gesamt = Decimal("0")
    for split in werte:
        kapital_gesamt += split.kapital_gv_chf
        waehrung_gesamt += split.waehrungs_gv_chf
    return FxSplit(kapital_gv_chf=kapital_gesamt, waehrungs_gv_chf=waehrung_gesamt)
