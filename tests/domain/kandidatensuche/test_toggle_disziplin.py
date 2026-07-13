"""Tests für die Toggle-Disziplin der Kandidatensuche (Story S-029).

Covers (kandidatensuche): AC9

`app.domain.kandidatensuche.toggle_disziplin.lade_suchprofil_falls_erlaubt`
deckt AC9/A1: für eine per Toggle deaktivierte Anlageklasse wird kein
Suchprofil geladen und (transitiv, da nichts an die Datenquellen-Abfrage
übergeben wird) keine Datenquellen-Abfrage ausgelöst."""

from __future__ import annotations

from app.contracts.anlageklassen_config import ToggleZustand
from app.contracts.kandidatensuche import Suchprofil
from app.domain.kandidatensuche.toggle_disziplin import lade_suchprofil_falls_erlaubt

PROFIL_KLASSE_1 = Suchprofil(anlageklasse=1)


def test_aktive_klasse_laedt_das_registrierte_suchprofil() -> None:
    """@trace kandidatensuche#AC9 — bei `aktiv=True` (Normalbetrieb) wird
    das registrierte Profil ganz normal geladen."""
    registry = {1: PROFIL_KLASSE_1}

    profil = lade_suchprofil_falls_erlaubt(
        registry, anlageklasse=1, zustand=ToggleZustand(aktiv=True)
    )

    assert profil == PROFIL_KLASSE_1


def test_inaktive_klasse_ohne_offene_positionen_laedt_kein_profil() -> None:
    """@trace kandidatensuche#AC9 — deckt A1: "Für eine per Toggle
    deaktivierte Anlageklasse wird kein Suchprofil geladen und keine
    Datenquellen-Abfrage ausgelöst" — die Funktion liefert `None`, obwohl
    ein Profil für diese Klasse registriert ist."""
    registry = {1: PROFIL_KLASSE_1}

    profil = lade_suchprofil_falls_erlaubt(
        registry,
        anlageklasse=1,
        zustand=ToggleZustand(aktiv=False, hat_offene_positionen=False),
    )

    assert profil is None


def test_inaktive_klasse_mit_offenen_positionen_laedt_trotzdem_kein_neues_suchprofil() -> None:
    """@trace kandidatensuche#AC9 — offene Positionen erlauben laut
    Toggle-Guard nur Bestandspflege, NICHT neue Verarbeitung/Kandidatensuche
    (AC5 der anlageklassen-config-Spec) — auch mit offenen Positionen bleibt
    `neue_verarbeitung_erlaubt=False`, also weiterhin kein Suchprofil."""
    registry = {1: PROFIL_KLASSE_1}

    profil = lade_suchprofil_falls_erlaubt(
        registry,
        anlageklasse=1,
        zustand=ToggleZustand(aktiv=False, hat_offene_positionen=True),
    )

    assert profil is None


def test_toggle_gate_greift_bevor_die_registry_ueberhaupt_befragt_wird() -> None:
    """@trace kandidatensuche#AC9 — selbst wenn KEIN Profil für die Klasse
    registriert ist, verhält sich eine inaktive Klasse identisch (`None`) —
    das Toggle-Gate ist unabhängig vom Registry-Inhalt."""
    profil = lade_suchprofil_falls_erlaubt({}, anlageklasse=1, zustand=ToggleZustand(aktiv=False))

    assert profil is None


def test_reaktivierung_erlaubt_sofort_wieder_das_laden_des_suchprofils() -> None:
    """@trace kandidatensuche#AC9 — nach Reaktivierung (`aktiv=True`) wird
    das Profil sofort wieder geladen (Toggle-Guard ist zustandslos, keine
    rückwirkende Sperre)."""
    registry = {1: PROFIL_KLASSE_1}

    waehrend_inaktiv = lade_suchprofil_falls_erlaubt(
        registry, anlageklasse=1, zustand=ToggleZustand(aktiv=False)
    )
    nach_reaktivierung = lade_suchprofil_falls_erlaubt(
        registry, anlageklasse=1, zustand=ToggleZustand(aktiv=True)
    )

    assert waehrend_inaktiv is None
    assert nach_reaktivierung == PROFIL_KLASSE_1
