"""Pre-Trade-Kostenkalkulation & Mindest-Ordergrösse (Story S-041, Spec
`docs/specs/sizing.md` AC5/AC6).

Reiner Domain-Kern (architecture.md §4 P1/P3): keine I/O, kein LLM, keine
DB — Kosten und Kapitalbasis kommen als Parameter herein. Kombiniert den
Risiko-Anteil des Kapitals (`risiko_pct`, Story S-039,
`app.domain.sizing.position_sizing.berechne_positionsgroesse`) mit einer
Kapitalbasis (CHF) und den bereits vorberechneten erwarteten Kosten
(`ErwarteteKosten`, Story S-017,
`app.db.trading_platform.berechne_erwartete_kosten`) zur absoluten
Ordergrösse:

- **AC5** — Pre-Trade-Kostenkalkulation: die geplante Brutto-Ordergrösse
  (`risiko_pct * kapitalbasis_chf`) wird um die erwarteten Kosten
  (Courtage + Spread + geschätzte Slippage, bereits aggregiert in
  `ErwarteteKosten.gesamtkosten_chf`) reduziert ("sie reduzieren die
  Grösse"). Verbleibt danach keine positive Netto-Grösse (`<= 0`, "kein
  positiver erwarteter Gewinn"), wird kein Trade erzeugt
  (`verworfen="kosten-uebersteigen-ertrag"`).
- **AC6** — Mindest-Ordergrösse: unterschreitet die verbleibende
  Netto-Ordergrösse (nach AC5) die konfigurierte Mindest-Ordergrösse
  (`OrdergroessenKonfiguration.mindest_ordergroesse_chf`, Default
  provisorisch, konfigurierbar), wird ebenfalls kein Auftrag erzeugt
  (`verworfen="unter-mindest-ordergroesse"`, deckt E2). Bei exakter
  Übereinstimmung (Netto-Grösse == Mindest-Ordergrösse) gilt die Grenze
  als erreicht — kein Verwerfen ("unterschreitet" ist eine strikte
  Ungleichung).

`erwartete_kosten` kommt bereits fertig berechnet herein (Parameter statt
DB-Zugriff, P1) — ein künftiger Orchestrierungs-Layer berechnet sie vorab
z.B. über `app.db.trading_platform.berechne_erwartete_kosten(
order_wert_chf=<Brutto-Schätzung aus risiko_pct * kapitalbasis_chf>)`.

Weder die vorgelagerte Kelly-/Cap-Berechnung (AC1–AC4, S-039) noch die
Kosten-Herleitung selbst (AC11, S-017) sind Teil dieser Story — dieses
Modul verdrahtet ausschliesslich AC5/AC6 gegen die bereits vorliegenden
Werte beider Vorgänger-Storys.
"""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal

from app.contracts.ausfuehrung_paper import ErwarteteKosten
from app.contracts.sizing import OrdergroessenErgebnis, OrdergroessenKonfiguration

#: Rundungsraster für CHF-Geldbeträge (NUMERIC(20,8)-kompatibel, P7/ADR-010)
#: — kaufmännisch gerundet (`ROUND_HALF_UP`), analog zu
#: `app.domain.portfolio.position_booking._quantize_geld`.
_GELD_QUANTUM = Decimal("0.00000001")


def _quantize_geld(wert: Decimal) -> Decimal:
    return wert.quantize(_GELD_QUANTUM, rounding=ROUND_HALF_UP)


def berechne_ordergroesse(
    *,
    titel_id: str,
    risiko_pct: Decimal,
    kapitalbasis_chf: Decimal,
    erwartete_kosten: ErwarteteKosten,
    konfiguration: OrdergroessenKonfiguration | None = None,
) -> OrdergroessenErgebnis:
    """AC5/AC6: kombiniert `risiko_pct` (S-039) + `kapitalbasis_chf` +
    `erwartete_kosten` (S-017) zur absoluten Netto-Ordergrösse und prüft
    nacheinander beide Schwellen — zuerst den Kostenabzug (AC5), danach
    die Mindest-Ordergrösse auf der resultierenden Netto-Grösse (AC6).

    Raises:
        ValueError: `risiko_pct` liegt ausserhalb `[0, 1]` (keine gültige
            Kapitalanteils-Grösse) oder `kapitalbasis_chf <= 0` (keine
            gültige Kapitalbasis).
    """
    if not (Decimal(0) <= risiko_pct <= Decimal(1)):
        raise ValueError(f"risiko_pct muss in [0, 1] liegen, war {risiko_pct!r}.")
    if kapitalbasis_chf <= 0:
        raise ValueError(f"kapitalbasis_chf muss > 0 sein, war {kapitalbasis_chf!r}.")

    aktive_konfiguration = konfiguration or OrdergroessenKonfiguration()

    ordergroesse_brutto_chf = _quantize_geld(risiko_pct * kapitalbasis_chf)
    ordergroesse_netto_chf = _quantize_geld(
        ordergroesse_brutto_chf - erwartete_kosten.gesamtkosten_chf
    )

    if ordergroesse_netto_chf <= 0:  # AC5: kein positiver erwarteter Gewinn mehr
        return OrdergroessenErgebnis(
            titel_id=titel_id,
            ordergroesse_chf=Decimal(0),
            ordergroesse_brutto_chf=ordergroesse_brutto_chf,
            kosten_chf=_quantize_geld(erwartete_kosten.gesamtkosten_chf),
            verworfen="kosten-uebersteigen-ertrag",
        )

    if ordergroesse_netto_chf < aktive_konfiguration.mindest_ordergroesse_chf:  # AC6, E2
        return OrdergroessenErgebnis(
            titel_id=titel_id,
            ordergroesse_chf=Decimal(0),
            ordergroesse_brutto_chf=ordergroesse_brutto_chf,
            kosten_chf=_quantize_geld(erwartete_kosten.gesamtkosten_chf),
            verworfen="unter-mindest-ordergroesse",
        )

    return OrdergroessenErgebnis(
        titel_id=titel_id,
        ordergroesse_chf=ordergroesse_netto_chf,
        ordergroesse_brutto_chf=ordergroesse_brutto_chf,
        kosten_chf=erwartete_kosten.gesamtkosten_chf,
        verworfen=None,
    )


__all__ = ["berechne_ordergroesse"]
