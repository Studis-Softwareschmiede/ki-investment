"""Kleine, modulübergreifend genutzte DB-Layer-Hilfsfunktionen.

Bisher genutzt von `app.db.bronze`, `app.db.validation`, `app.db.silver`
(alle drei vergleichen Zeitstempel dialektübergreifend, AC9/AC10/AC3) —
vormals als privates `app.db.bronze._als_utc_naiv` dreifach importiert
(FEATURE-NOTES-Handoff S-024 nannte den Schwellenwert "bei Mehrfachnutzung
verschieben" bereits vorab; Iteration-2-Reviewer-Befund zieht dies nach).
"""

from __future__ import annotations

from datetime import UTC, datetime


def als_utc_naiv(zeitpunkt: datetime) -> datetime:
    """Normalisiert einen Zeitpunkt fuer den Inhaltsvergleich (AC9/AC10/AC3).

    SQLite (Test-Backend, kein natives `TIMESTAMPTZ`) liefert `tzinfo` bei
    gespeicherten Zeitstempeln nicht zuverlaessig zurueck, waehrend
    PostgreSQL (`TIMESTAMPTZ`, Produktiv-Backend) `tzinfo` konsistent
    bewahrt. Der Vergleich normalisiert daher auf UTC-naiv, damit derselbe
    Zeitpunkt unabhaengig vom Backend als identisch erkannt wird — der
    fachliche Moment (nicht die Wall-Clock-Repraesentation) entscheidet.
    """
    if zeitpunkt.tzinfo is not None:
        return zeitpunkt.astimezone(UTC).replace(tzinfo=None)
    return zeitpunkt
