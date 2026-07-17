"""Frische-Fenster-Prüfung (Story S-032, Spec
`docs/specs/depot-ueberwachung.md` AC9, deckt E1: "Fällt für einen Titel
das Signal-Bündel aus oder ist es älter als das konfigurierte
Frische-Fenster, wird der Titel als 'nicht bewertbar' markiert und
protokolliert; es wird kein Ereignis fabriziert (kein Verkaufsimpuls aus
fehlenden Daten).").

Reiner Domain-Kern (architecture.md §4 P1/P3): keine I/O, kein
SQLAlchemy. `ist_titel_bewertbar` ist die EINE Stelle, die AC9 auswertet."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.contracts.dateneingang import SignalBuendel


def ist_titel_bewertbar(
    signal_buendel: SignalBuendel | None, *, jetzt: datetime, frische_fenster: timedelta
) -> bool:
    """AC9: `False`, wenn `signal_buendel` fehlt (`None`) ODER strukturell
    leer ist (`signale == []`, siehe `app.orchestration.datasource_query`
    "kein Wert wird geschätzt") ODER das jüngste enthaltene Signal älter
    als `frische_fenster` ist (relativ zu `jetzt`) — sonst `True`.

    Bei mehreren Signalen (mehrere beitragende Quellen) zählt das
    ZEITLICH NEUESTE (`beobachtet_am`, `max()`): ein Titel gilt als
    bewertbar, sobald MINDESTENS EINE Quelle noch innerhalb des
    Frische-Fensters liegt (konservativ zugunsten der Überwachung, nicht
    zugunsten eines fabrizierten Ereignisses — die inhaltliche
    Auswertung/Gewichtung einzelner veralteter Quellen bleibt der
    Folge-Story, AC4-AC7, überlassen)."""
    if signal_buendel is None or not signal_buendel.signale:
        return False
    neuestes_signal = max(signal.beobachtet_am for signal in signal_buendel.signale)
    return (_als_utc_aware(jetzt) - _als_utc_aware(neuestes_signal)) <= frische_fenster


def _als_utc_aware(zeitpunkt: datetime) -> datetime:
    """Normalisiert einen Zeitpunkt auf UTC-aware für einen
    dialektübergreifend korrekten Vergleich: SQLite (Test-Backend) liefert
    bei `TIMESTAMP(timezone=True)`-Spalten `tzinfo` nicht zuverlässig
    zurück, während PostgreSQL (Produktiv-Backend) `tzinfo` konsistent
    bewahrt (analog `app.db.utils.als_utc_naiv`, hier UTC-AWARE statt
    UTC-naiv — der Domain-Kern importiert bewusst nichts aus `app.db`,
    P1, und normalisiert daher lokal in die jeweils andere Richtung)."""
    if zeitpunkt.tzinfo is None:
        return zeitpunkt.replace(tzinfo=UTC)
    return zeitpunkt.astimezone(UTC)


__all__ = ["ist_titel_bewertbar"]
