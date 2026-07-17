"""Regel-Governance der Kandidatensuche (Story S-057, Spec
`docs/specs/kandidatensuche.md` AC8, deckt A3: "Eine geänderte/neue
Suchregel wird nur übernommen, wenn sie das Validierungs-Gate durchlaufen
hat (Ampel 🟢); Vorschläge ohne Gate-Freigabe verändern die aktive Suche
nicht.").

Reiner Domain-Kern (architecture.md §4 P1/P3, Modul 3 "Suchkriteria"):
`uebernehme_regelaenderung` ist die EINZIGE in dieser Domäne vorgesehene
Stelle, über die ein `Regelvorschlag` (Vertrag "Input aus Lernschleife")
in eine `SuchprofilRegistry` einfliesst — ausserhalb dieser Funktion gibt
es keinen weiteren, hier definierten Weg, eine Registry aus einem
Regelvorschlag zu aktualisieren (Nicht-Ziele: die Berechnung des
Gate-Ergebnisses selbst — Ampel-Herleitung, Stufe A/B — ist Sache der
Lernschleife-Spec/Stories S-058-S-062, hier NUR konsumiert)."""

from __future__ import annotations

from app.contracts.kandidatensuche import Regelvorschlag, SuchprofilRegistry


def uebernehme_regelaenderung(
    registry: SuchprofilRegistry,
    vorschlag: Regelvorschlag,
) -> SuchprofilRegistry:
    """AC8: übernimmt `vorschlag.profil` NUR bei `vorschlag.ampel ==
    "gruen"` in eine neue Registry (Original bleibt unverändert, kein
    In-Place-Mutieren). Bei `"gelb"`/`"rot"` liefert die Funktion die
    unveränderte `registry` zurück — der Vorschlag wird verworfen/geparkt,
    nie automatisch aktiv (Edge-Case "Regelvorschlag ohne Gate-Freigabe →
    verworfen/geparkt, nie automatisch aktiv")."""
    if vorschlag.ampel != "gruen":
        return registry
    aktualisiert = dict(registry)
    aktualisiert[vorschlag.profil.anlageklasse] = vorschlag.profil
    return aktualisiert


__all__ = ["uebernehme_regelaenderung"]
