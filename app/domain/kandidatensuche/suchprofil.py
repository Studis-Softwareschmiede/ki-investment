"""Suchprofil-Framework (Story S-029, Spec `docs/specs/kandidatensuche.md`
AC1/AC10).

Reiner Domain-Kern (architecture.md §4 P1/P3, Modul 3 "Suchkriteria" —
Layer `domain`): kein I/O, kein SQLAlchemy, keine `app.config`-Imports.
`lade_suchprofil` ist die EINZIGE Stelle, die eine `SuchprofilRegistry`
befragt (AC1: "Die Suche nutzt je Anlageklasse ein eigenes Suchprofil; es
gibt keinen einheitlichen Filter über alle Klassen. Ein Titel wird nur
gegen das Profil seiner Anlageklasse geprüft.") — es existiert strukturell
kein Fallback auf ein anderes/geteiltes Profil.
"""

from __future__ import annotations

from app.contracts.kandidatensuche import (
    Suchprofil,
    SuchprofilOverride,
    SuchprofilOverrides,
    SuchprofilRegistry,
)


def lade_suchprofil(
    registry: SuchprofilRegistry,
    anlageklasse: int,
    overrides: SuchprofilOverrides | None = None,
) -> Suchprofil | None:
    """AC1: liefert AUSSCHLIESSLICH das für `anlageklasse` registrierte
    Profil (oder `None`, wenn für diese Klasse keines registriert ist) —
    niemals ein Profil einer anderen Klasse oder einen geteilten Default
    (kein "einheitlicher Filter über alle Klassen").

    `overrides` wendet einen etwaigen AC7/AC10-Konfig-Override für GENAU
    diese Klasse an (`app.config.Settings.kandidatensuche_profil_overrides`,
    ohne Codeänderung überschreibbar)."""
    profil = registry.get(anlageklasse)
    if profil is None:
        return None
    if overrides is None:
        return profil
    return wende_override_an(profil, overrides.get(anlageklasse))


def wende_override_an(profil: Suchprofil, override: SuchprofilOverride | None) -> Suchprofil:
    """AC7/AC10: wendet einen Konfig-Override ohne Codeänderung an —
    `modus` wird ersetzt (falls im Override gesetzt), `schwellen` wird
    GEMERGED (nur die im Override genannten Keys werden ersetzt, alle
    anderen Schwellen des Profils bleiben unverändert). Ohne Override
    (`None`) oder einen leeren Override liefert die Funktion `profil`
    unverändert (identisch, nicht bloss gleichwertig) zurück."""
    if override is None:
        return profil

    aktualisierte_felder: dict[str, object] = {}
    if override.schwellen:
        neue_schwellen = dict(profil.schwellen)
        neue_schwellen.update(override.schwellen)
        aktualisierte_felder["schwellen"] = neue_schwellen
    if override.modus is not None:
        aktualisierte_felder["modus"] = override.modus

    if not aktualisierte_felder:
        return profil
    return profil.model_copy(update=aktualisierte_felder)


__all__ = ["lade_suchprofil", "wende_override_an"]
