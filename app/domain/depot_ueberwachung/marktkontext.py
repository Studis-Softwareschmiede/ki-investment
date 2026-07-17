"""Marktkontext-Normierung von Kursbewegungen (Story S-033, Spec
`docs/specs/depot-ueberwachung.md` AC5, Main-Success-Scenario Schritt 4:
"normiert Kursbewegungen gegen den Marktkontext").

Reiner Domain-Kern (architecture.md §4 P1/P3): keine I/O.
`normiere_kursbewegung` ist die EINE Stelle, die AC5 auswertet: die
normierte Bewegung ist die Übertreibung/Abweichung des Titels GEGENÜBER
der gleichzeitigen Marktbewegung (`titel_bewegung - markt_bewegung`) — ein
Titel, der genauso stark fällt wie der Markt, hat eine normierte Bewegung
von `0` (kein titelspezifisches Ereignis). Fehlt der Marktreferenz-Wert
(`markt_bewegung is None`), fällt die Bewertung konservativ auf den
Absolutwert zurück (Edge-Case der Spec: "Marktkontext-Normierung braucht
einen Marktreferenz-Wert; fehlt dieser, wird konservativ auf
Absolut-Bewertung zurückgefallen und dies protokolliert") — das
`fallback_verwendet`-Flag im Ergebnis ist die testbare Grundlage dafür;
die tatsächliche Protokollierung obliegt dem (künftigen) Aufrufer, sobald
ein Markt-Referenz-Adapter existiert (Cold-Start, analog
`app.contracts.depot_ueberwachung.TitelSignalRohdaten`)."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True)
class NormierteKursbewegung:
    """Ergebnis der AC5-Normierung: `normierte_bewegung` ist der Wert, den
    `app.domain.depot_ueberwachung.ereignis_erzeugung` gegen die
    `relativer_kurssturz`-Schwelle prüft. `fallback_verwendet=True`
    bedeutet: kein Marktreferenz-Wert vorhanden, `normierte_bewegung`
    entspricht dann `titel_bewegung` unverändert (Absolut-Bewertung)."""

    titel_bewegung: Decimal
    markt_bewegung: Decimal | None
    normierte_bewegung: Decimal
    fallback_verwendet: bool


def normiere_kursbewegung(
    titel_bewegung: Decimal, markt_bewegung: Decimal | None
) -> NormierteKursbewegung:
    """AC5: normiert `titel_bewegung` (relative Kursänderung, z. B.
    `Decimal("-0.10")` für -10 %) gegen `markt_bewegung` (relative
    Marktbewegung im selben Zeitraum) — Spec-Beispiel: "-10 % an einem
    -8 %-Markttag löst nicht dieselbe Bewertung aus wie -10 % an einem
    flachen Tag": erster Fall normiert auf `-0.02` (Übertreibung ggü. dem
    Markt), zweiter Fall (Markt `0`) bleibt bei `-0.10`. Fehlt
    `markt_bewegung`, wird konservativ auf den Absolutwert
    zurückgefallen (`fallback_verwendet=True`)."""
    if markt_bewegung is None:
        return NormierteKursbewegung(
            titel_bewegung=titel_bewegung,
            markt_bewegung=None,
            normierte_bewegung=titel_bewegung,
            fallback_verwendet=True,
        )
    return NormierteKursbewegung(
        titel_bewegung=titel_bewegung,
        markt_bewegung=markt_bewegung,
        normierte_bewegung=titel_bewegung - markt_bewegung,
        fallback_verwendet=False,
    )


__all__ = ["NormierteKursbewegung", "normiere_kursbewegung"]
