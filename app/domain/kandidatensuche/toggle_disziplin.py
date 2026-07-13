"""Toggle-Disziplin der Kandidatensuche (Story S-029, Spec
`docs/specs/kandidatensuche.md` AC9, deckt A1: "Für eine per Toggle
deaktivierte Anlageklasse wird kein Suchprofil geladen und keine
Datenquellen-Abfrage ausgelöst.").

Reiner Domain-Kern, dockt an den bestehenden Toggle-Guard-Konsumenten-
Kontrakt (S-019, `app.domain.assetclasses.toggle_guard`) an — baut die
AC4/AC5-Regel der `anlageklassen-config`-Spec NICHT nach (Anti-
Duplikations-Vorgabe des Toggle-Guard-Modul-Docstrings: "jedes der fünf in
der Spec genannten Konsumenten-Module ... fragt sie vor jeder Aktion ...
ab, statt die Regel selbst nachzubauen"), sondern konsumiert sie.
"""

from __future__ import annotations

from app.contracts.anlageklassen_config import ToggleZustand
from app.contracts.kandidatensuche import Suchprofil, SuchprofilOverrides, SuchprofilRegistry
from app.domain.assetclasses.toggle_guard import pruefe_verarbeitungserlaubnis
from app.domain.kandidatensuche.suchprofil import lade_suchprofil


def lade_suchprofil_falls_erlaubt(
    registry: SuchprofilRegistry,
    anlageklasse: int,
    zustand: ToggleZustand,
    overrides: SuchprofilOverrides | None = None,
) -> Suchprofil | None:
    """AC9: für eine per Toggle deaktivierte Anlageklasse
    (`neue_verarbeitung_erlaubt = False`, siehe `toggle_guard`) wird
    `registry` NICHT befragt — es wird kein Suchprofil geladen (keine
    Verarbeitung, keine Datenkosten). Bei erlaubter neuer Verarbeitung
    delegiert die Funktion unverändert an `lade_suchprofil` (AC1).

    Da diese Funktion die einzige Andockstelle für ein nachgelagertes
    "Filterkriterien an die Datenquellen-Abfrage übergeben" ist (siehe
    `app.domain.kandidatensuche.kandidatensuche.erstelle_filterkriterien`),
    löst eine deaktivierte Klasse transitiv auch KEINE Datenquellen-Abfrage
    aus — es gibt nichts, das an sie übergeben werden könnte."""
    erlaubnis = pruefe_verarbeitungserlaubnis(zustand)
    if not erlaubnis.neue_verarbeitung_erlaubt:
        return None
    return lade_suchprofil(registry, anlageklasse, overrides)


__all__ = ["lade_suchprofil_falls_erlaubt"]
