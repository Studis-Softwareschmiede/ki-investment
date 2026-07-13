"""Tests für das Suchprofil-Framework (Story S-029).

Covers (kandidatensuche): AC1, AC7, AC10

`app.domain.kandidatensuche.suchprofil.lade_suchprofil` ist die EINZIGE
Nachschlagestelle für ein Suchprofil (AC1: "kein einheitlicher Filter über
alle Klassen"); `wende_override_an` deckt die AC7/AC10-Konfig-Override-
Mechanik (Modus-Ersetzung + Schwellen-Merge, ohne Codeänderung)."""

from __future__ import annotations

from decimal import Decimal

from app.contracts.kandidatensuche import Suchprofil, SuchprofilOverride
from app.domain.kandidatensuche.suchprofil import lade_suchprofil, wende_override_an

PROFIL_KLASSE_1 = Suchprofil(
    anlageklasse=1,
    pflicht_bedingungen=["rvol_ueber_2x"],
    schwellen={"rvol_faktor": Decimal("2")},
)
PROFIL_KLASSE_7 = Suchprofil(
    anlageklasse=7,
    pflicht_bedingungen=["rvol_ueber_2x"],
    schwellen={"rvol_faktor": Decimal("2")},
)


def test_lade_suchprofil_liefert_nur_das_profil_der_eigenen_klasse() -> None:
    """@trace kandidatensuche#AC1 — "Ein Titel wird nur gegen das Profil
    seiner Anlageklasse geprüft": bei zwei registrierten Profilen liefert
    die Abfrage für Klasse 1 EXAKT das Klasse-1-Profil, nicht das
    Klasse-7-Profil (kein einheitlicher/geteilter Filter)."""
    registry = {1: PROFIL_KLASSE_1, 7: PROFIL_KLASSE_7}

    profil = lade_suchprofil(registry, anlageklasse=1)

    assert profil == PROFIL_KLASSE_1
    assert profil != PROFIL_KLASSE_7


def test_lade_suchprofil_liefert_none_ohne_fallback_fuer_unregistrierte_klasse() -> None:
    """@trace kandidatensuche#AC1 — für eine Klasse ohne registriertes
    Profil gibt es KEINEN Fallback auf ein anderes/geteiltes Profil, die
    Funktion liefert `None`."""
    registry = {1: PROFIL_KLASSE_1}

    assert lade_suchprofil(registry, anlageklasse=2) is None


def test_lade_suchprofil_ohne_overrides_liefert_profil_unveraendert() -> None:
    """@trace kandidatensuche#AC1 — `overrides=None` (Default) ändert nichts
    am registrierten Profil."""
    registry = {1: PROFIL_KLASSE_1}

    assert lade_suchprofil(registry, anlageklasse=1) == PROFIL_KLASSE_1


def test_lade_suchprofil_wendet_override_fuer_die_eigene_klasse_an() -> None:
    """@trace kandidatensuche#AC7,AC10 — ein Override für Klasse 1 wirkt
    NUR auf das Klasse-1-Profil, ein für Klasse 7 registriertes Profil
    bleibt unverändert (kein klassenübergreifendes Durchsickern)."""
    registry = {1: PROFIL_KLASSE_1, 7: PROFIL_KLASSE_7}
    overrides = {1: SuchprofilOverride(modus="periodisch")}

    profil_1 = lade_suchprofil(registry, anlageklasse=1, overrides=overrides)
    profil_7 = lade_suchprofil(registry, anlageklasse=7, overrides=overrides)

    assert profil_1.modus == "periodisch"
    assert profil_7.modus == "eventbasiert"


def test_wende_override_an_ohne_override_liefert_identisches_profil() -> None:
    """@trace kandidatensuche#AC7,AC10 — `override=None` liefert exakt das
    unveränderte Profil-Objekt zurück (keine unnötige Kopie)."""
    assert wende_override_an(PROFIL_KLASSE_1, None) is PROFIL_KLASSE_1


def test_wende_override_an_leerer_override_liefert_identisches_profil() -> None:
    """@trace kandidatensuche#AC7,AC10 — ein Override ohne gesetzten Modus
    und ohne Schwellen ändert das Profil nicht (Identität, nicht nur
    Gleichheit)."""
    leer = SuchprofilOverride()
    assert wende_override_an(PROFIL_KLASSE_1, leer) is PROFIL_KLASSE_1


def test_wende_override_an_ersetzt_modus() -> None:
    """@trace kandidatensuche#AC7 — ein gesetzter `modus` im Override
    ersetzt den Suchmodus des Profils, ohne Codeänderung."""
    override = SuchprofilOverride(modus="periodisch")

    aktualisiert = wende_override_an(PROFIL_KLASSE_1, override)

    assert aktualisiert.modus == "periodisch"
    assert PROFIL_KLASSE_1.modus == "eventbasiert"  # Original bleibt unverändert


def test_wende_override_an_merged_schwellen_statt_vollstaendig_zu_ersetzen() -> None:
    """@trace kandidatensuche#AC10 — der Schwellen-Override MERGED: nur
    der im Override genannte Key wird ersetzt, andere Schwellen-Keys des
    Profils bleiben erhalten (im Unterschied zum Full-Replace-Muster von
    TOLERANZ_CONFIG)."""
    profil = Suchprofil(
        anlageklasse=1,
        schwellen={"rvol_faktor": Decimal("2"), "rsi_schwelle": Decimal("70")},
    )
    override = SuchprofilOverride(schwellen={"rvol_faktor": Decimal("3")})

    aktualisiert = wende_override_an(profil, override)

    assert aktualisiert.schwellen == {
        "rvol_faktor": Decimal("3"),
        "rsi_schwelle": Decimal("70"),
    }


def test_wende_override_an_kombiniert_modus_und_schwellen_override() -> None:
    """@trace kandidatensuche#AC7,AC10 — Modus- und Schwellen-Override
    lassen sich in einem Aufruf gemeinsam anwenden."""
    override = SuchprofilOverride(modus="periodisch", schwellen={"rvol_faktor": Decimal("1.5")})

    aktualisiert = wende_override_an(PROFIL_KLASSE_1, override)

    assert aktualisiert.modus == "periodisch"
    assert aktualisiert.schwellen == {"rvol_faktor": Decimal("1.5")}
