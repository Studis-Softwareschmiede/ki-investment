"""Input-Vollständigkeit gehaltener Titel (Story S-032, Spec
`docs/specs/depot-ueberwachung.md` AC1).

Reiner Domain-Kern (architecture.md §4 P1/P3): keine I/O, kein
SQLAlchemy. `ermittle_fehlende_felder` ist die EINE Stelle, die die AC1-
Vollständigkeitsregel prüft — der Aufrufer
(`app.orchestration.depot_ueberwachung.fuehre_monitoring_zyklus_aus`)
protokolliert einen Titel mit fehlenden Feldern (AC1: "wird der Titel als
unvollständig protokolliert und nicht stillschweigend übersprungen") und
lässt ihn aus der weiteren Verarbeitung dieses Zyklus fallen (analog zum
AC9/E1-Muster "nicht bewertbar protokolliert, kein Ereignis fabriziert" —
strukturell dieselbe "Gate davor, sichtbar loggen statt stillschweigend
verwerfen"-Disziplin).

**`exit_regeln`-Prüfung, Cold-Start-Hinweis:** `app.domain.portfolio.ports
.ExitRegelnBestand` trägt aktuell IMMER ausschliesslich `None`-Felder,
solange keine Story eine `exit_rule`-Zeile persistiert (S-037/S-038, siehe
`app.adapters.repositories.position_repository._exit_regeln_aus_zeile`-
Docstring) — bis dahin gilt jedes gehaltene Exit-Regel-Bündel korrekt als
strukturell fehlend (kein Vortäuschen einer nicht existierenden
Persistenz)."""

from __future__ import annotations

from dataclasses import fields

from app.domain.portfolio.portfolio_aggregate import TitelStrategieExitRegeln
from app.domain.portfolio.ports import ExitRegelnBestand


def ermittle_fehlende_felder(titel: TitelStrategieExitRegeln) -> list[str]:
    """AC1: liefert die Namen der fehlenden Pflichtfelder von `titel`
    (`titel_id, anlageklasse, strategie, exit_regeln`) — leere Liste, wenn
    alle vier vorhanden sind. Prüfreihenfolge ist deterministisch (immer
    `titel_id, anlageklasse, strategie, exit_regeln`), für stabile
    Protokoll-Texte."""
    fehlend: list[str] = []
    if _ist_leerer_string(titel.titel_id):
        fehlend.append("titel_id")
    if titel.anlageklasse is None or not (1 <= titel.anlageklasse <= 11):
        fehlend.append("anlageklasse")
    if _ist_leerer_string(titel.strategie):
        fehlend.append("strategie")
    if _sind_exit_regeln_leer(titel.exit_regeln):
        fehlend.append("exit_regeln")
    return fehlend


def _ist_leerer_string(wert: str | None) -> bool:
    """Fehlend heisst hier `None` ODER ein Leer-/Whitespace-String (analog
    zu `app.contracts.depot._ist_leer`)."""
    if wert is None:
        return True
    return wert.strip() == ""


def _sind_exit_regeln_leer(exit_regeln: ExitRegelnBestand) -> bool:
    """`True`, wenn ALLE Felder von `exit_regeln` `None` sind — siehe
    Moduldocstring (Cold-Start: aktuell strukturell immer der Fall, bis
    `exit_rule`-Persistenz existiert)."""
    return all(getattr(exit_regeln, feld.name) is None for feld in fields(exit_regeln))


__all__ = ["ermittle_fehlende_felder"]
