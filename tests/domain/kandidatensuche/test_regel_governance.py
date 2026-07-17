"""Tests für die Regel-Governance der Kandidatensuche (Story S-057).

Covers (kandidatensuche): AC8

`uebernehme_regelaenderung` ist die einzige Andockstelle, über die ein
`Regelvorschlag` aus der Lernschleife in eine `SuchprofilRegistry`
einfliessen kann (AC8: "ausschliesslich über das Validierungs-Gate") —
nur bei Ampel-Status `"gruen"` wird die Registry aktualisiert."""

from __future__ import annotations

from decimal import Decimal

from app.contracts.kandidatensuche import Regelvorschlag, Suchprofil
from app.domain.kandidatensuche.regel_governance import uebernehme_regelaenderung

PROFIL_KLASSE_1_ALT = Suchprofil(
    anlageklasse=1,
    pflicht_bedingungen=["rvol_ueber_2x"],
    schwellen={"rvol_faktor": Decimal("2")},
)
PROFIL_KLASSE_1_NEU = Suchprofil(
    anlageklasse=1,
    pflicht_bedingungen=["rvol_ueber_2x"],
    schwellen={"rvol_faktor": Decimal("2.5")},
)


def test_gruene_ampel_uebernimmt_die_regeländerung_in_die_registry() -> None:
    """@trace kandidatensuche#AC8 — ein Regelvorschlag mit Ampel "gruen"
    (Gate-Freigabe) ersetzt das bestehende Profil der betroffenen
    Anlageklasse in der Registry."""
    registry = {1: PROFIL_KLASSE_1_ALT}
    vorschlag = Regelvorschlag(profil=PROFIL_KLASSE_1_NEU, ampel="gruen")

    aktualisiert = uebernehme_regelaenderung(registry, vorschlag)

    assert aktualisiert[1] == PROFIL_KLASSE_1_NEU


def test_gelbe_ampel_aendert_die_aktive_suche_nicht() -> None:
    """@trace kandidatensuche#AC8 — ein Vorschlag mit Ampel "gelb" (Stufe A
    bestanden, Stufe B läuft noch) verändert die aktive Registry NICHT
    (Edge-Case "Regelvorschlag ohne Gate-Freigabe → verworfen/geparkt")."""
    registry = {1: PROFIL_KLASSE_1_ALT}
    vorschlag = Regelvorschlag(profil=PROFIL_KLASSE_1_NEU, ampel="gelb")

    aktualisiert = uebernehme_regelaenderung(registry, vorschlag)

    assert aktualisiert[1] == PROFIL_KLASSE_1_ALT


def test_rote_ampel_aendert_die_aktive_suche_nicht() -> None:
    """@trace kandidatensuche#AC8 — ein durchgefallener Vorschlag (Ampel
    "rot") verändert die aktive Registry ebenfalls nicht."""
    registry = {1: PROFIL_KLASSE_1_ALT}
    vorschlag = Regelvorschlag(profil=PROFIL_KLASSE_1_NEU, ampel="rot")

    aktualisiert = uebernehme_regelaenderung(registry, vorschlag)

    assert aktualisiert[1] == PROFIL_KLASSE_1_ALT


def test_regelaenderung_ohne_gate_freigabe_laesst_original_registry_unveraendert() -> None:
    """@trace kandidatensuche#AC8 — die als Argument übergebene Registry
    wird bei fehlender Gate-Freigabe nicht in-place mutiert (Original
    bleibt identisch, kein Seiteneffekt)."""
    registry = {1: PROFIL_KLASSE_1_ALT}
    vorschlag = Regelvorschlag(profil=PROFIL_KLASSE_1_NEU, ampel="rot")

    uebernehme_regelaenderung(registry, vorschlag)

    assert registry == {1: PROFIL_KLASSE_1_ALT}


def test_gruene_ampel_fuer_neue_klasse_ergaenzt_registry_ohne_andere_klassen() -> None:
    """@trace kandidatensuche#AC8,AC1 — ein gate-freigegebener Vorschlag für
    eine bislang unregistrierte Klasse ergänzt die Registry, bestehende
    Profile anderer Klassen bleiben unverändert (kein klassenübergreifendes
    Durchsickern, analog AC1)."""
    profil_klasse_7 = Suchprofil(anlageklasse=7, schwellen={"rvol_faktor": Decimal("2")})
    registry = {1: PROFIL_KLASSE_1_ALT}
    vorschlag = Regelvorschlag(profil=profil_klasse_7, ampel="gruen")

    aktualisiert = uebernehme_regelaenderung(registry, vorschlag)

    assert aktualisiert[1] == PROFIL_KLASSE_1_ALT
    assert aktualisiert[7] == profil_klasse_7
