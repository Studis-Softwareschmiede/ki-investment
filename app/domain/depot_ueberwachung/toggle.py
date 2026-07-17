"""Toggle-Ausnahme für gehaltene Titel (Story S-032, Spec
`docs/specs/depot-ueberwachung.md` AC8, deckt A1: "Ist die Anlageklasse
eines gehaltenen Titels per Feature-Toggle deaktiviert, bleibt die
Überwachung dieses Titels trotzdem aktiv").

Reiner Domain-Kern, dockt an den bestehenden Toggle-Guard-Konsumenten-
Kontrakt (S-019, `app.domain.assetclasses.toggle_guard`) an — baut die
AC4/AC5-Regel der `anlageklassen-config`-Spec NICHT nach (Anti-
Duplikations-Vorgabe des Toggle-Guard-Modul-Docstrings: "jedes der fünf in
der Spec genannten Konsumenten-Module ... fragt sie vor jeder Aktion ...
ab, statt die Regel selbst nachzubauen"), sondern konsumiert sie — analog
`app.domain.kandidatensuche.toggle_disziplin`."""

from __future__ import annotations

from app.contracts.anlageklassen_config import ToggleZustand
from app.domain.assetclasses.toggle_guard import pruefe_verarbeitungserlaubnis


def ist_ueberwachung_erlaubt(*, aktiv: bool) -> bool:
    """AC8: ein gehaltener Titel hat per Definition eine offene Position
    (`hat_offene_positionen=True`) — der Toggle-Guard liefert für diese
    Konstellation IMMER `bestandspflege_erlaubt=True`, unabhängig von
    `aktiv` (BR-017/BR-018, "ein Toggle darf niemals dazu führen, dass
    eine gehaltene Position blind wird"). Diese Funktion delegiert
    bewusst an den Guard statt die Regel hier zu wiederholen — der Aufruf
    selbst ist der Beleg, dass eine deaktivierte Klasse die Überwachung
    NICHT abschaltet."""
    erlaubnis = pruefe_verarbeitungserlaubnis(
        ToggleZustand(aktiv=aktiv, hat_offene_positionen=True)
    )
    return erlaubnis.bestandspflege_erlaubt


__all__ = ["ist_ueberwachung_erlaubt"]
