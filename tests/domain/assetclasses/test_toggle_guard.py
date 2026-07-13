"""Tests für den Toggle-Guard (Story S-019).

Covers (anlageklassen-config): AC4, AC5

`app.domain.assetclasses.toggle_guard.pruefe_verarbeitungserlaubnis` ist der
geteilte Konsumenten-Kontrakt für Kandidatensuche, Datenquellen-Abfrage,
Analyse, Handelsplattformen und Depotstrategie: eine inaktive Klasse löst
keine neue Verarbeitung/keinen Datenabruf aus (AC4), während Überwachung +
Exit-Ausführung offener Positionen bei Deaktivierung aktiv bleiben (AC5,
deckt A1) und Reaktivierung Neukäufe ohne rückwirkende Verarbeitung wieder
zulässt (Edge-Case der Spec).
"""

from __future__ import annotations

from app.contracts.anlageklassen_config import ToggleZustand, Verarbeitungserlaubnis
from app.domain.assetclasses.toggle_guard import pruefe_verarbeitungserlaubnis


def test_aktive_klasse_erlaubt_neue_verarbeitung_und_bestandspflege() -> None:
    """@trace anlageklassen-config#AC4 — bei `aktiv = True` sind sowohl neue
    Verarbeitung (Kandidatensuche/Datenabruf/neue Käufe) als auch
    Bestandspflege erlaubt (Normalbetrieb)."""
    erlaubnis = pruefe_verarbeitungserlaubnis(ToggleZustand(aktiv=True))

    assert erlaubnis == Verarbeitungserlaubnis(
        neue_verarbeitung_erlaubt=True, bestandspflege_erlaubt=True
    )


def test_inaktive_klasse_ohne_offene_positionen_sperrt_alles() -> None:
    """@trace anlageklassen-config#AC4 — eine inaktive Klasse ohne offene
    Positionen löst sofort keinerlei Verarbeitung und keinen Datenabruf aus
    (Edge-Case der Spec: "sofort keinerlei Verarbeitung/Datenabruf")."""
    erlaubnis = pruefe_verarbeitungserlaubnis(
        ToggleZustand(aktiv=False, hat_offene_positionen=False)
    )

    assert erlaubnis == Verarbeitungserlaubnis(
        neue_verarbeitung_erlaubt=False, bestandspflege_erlaubt=False
    )


def test_deaktivierung_mit_offenen_positionen_sperrt_nur_neue_kaeufe() -> None:
    """@trace anlageklassen-config#AC5 — wird eine Klasse mit offenen
    Positionen deaktiviert, unterbleiben neue Käufe, während Überwachung
    und Exit-Ausführung (Bestandspflege) aktiv bleiben (deckt A1)."""
    erlaubnis = pruefe_verarbeitungserlaubnis(
        ToggleZustand(aktiv=False, hat_offene_positionen=True)
    )

    assert erlaubnis.neue_verarbeitung_erlaubt is False
    assert erlaubnis.bestandspflege_erlaubt is True


def test_toggle_darf_nie_eine_gehaltene_position_unueberwacht_lassen() -> None:
    """@trace anlageklassen-config#AC5 — Kernsatz der AC: "Ein Toggle darf
    niemals dazu führen, dass eine gehaltene Position unüberwacht bleibt."
    Für jede Kombination aus `aktiv` bleibt `bestandspflege_erlaubt` `True`,
    sobald offene Positionen bestehen."""
    for aktiv in (True, False):
        erlaubnis = pruefe_verarbeitungserlaubnis(
            ToggleZustand(aktiv=aktiv, hat_offene_positionen=True)
        )
        assert erlaubnis.bestandspflege_erlaubt is True


def test_reaktivierung_erlaubt_neue_kaeufe_ohne_rueckwirkende_verarbeitung() -> None:
    """@trace anlageklassen-config#AC5 — Reaktivierung einer zuvor
    deaktivierten Klasse mit weiterhin offenen Positionen: neue Käufe sind
    sofort wieder zulässig; der Guard ist zustandslos, es gibt keine
    "rückwirkende Verarbeitung" der Inaktiv-Phase nachzuholen (Edge-Case der
    Spec)."""
    waehrend_inaktiv = pruefe_verarbeitungserlaubnis(
        ToggleZustand(aktiv=False, hat_offene_positionen=True)
    )
    assert waehrend_inaktiv.neue_verarbeitung_erlaubt is False

    nach_reaktivierung = pruefe_verarbeitungserlaubnis(
        ToggleZustand(aktiv=True, hat_offene_positionen=True)
    )
    assert nach_reaktivierung == Verarbeitungserlaubnis(
        neue_verarbeitung_erlaubt=True, bestandspflege_erlaubt=True
    )


def test_toggle_zustand_default_keine_offenen_positionen() -> None:
    """@trace anlageklassen-config#AC4 — `hat_offene_positionen` ist
    optional (Default `False`); ein Konsument, der nur den Aktiv-Zustand
    kennt (noch keine Positions-Domäne, Cold-Start), erhält damit korrekt
    das strikte AC4-Verhalten ohne Bestandspflege-Ausnahme."""
    erlaubnis = pruefe_verarbeitungserlaubnis(ToggleZustand(aktiv=False))

    assert erlaubnis.bestandspflege_erlaubt is False
