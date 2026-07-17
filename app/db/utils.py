"""Kleine, modulübergreifend genutzte DB-Layer-Hilfsfunktionen.

Bisher genutzt von `app.db.bronze`, `app.db.validation`, `app.db.silver`
(alle drei vergleichen Zeitstempel dialektübergreifend, AC9/AC10/AC3) —
vormals als privates `app.db.bronze._als_utc_naiv` dreifach importiert
(FEATURE-NOTES-Handoff S-024 nannte den Schwellenwert "bei Mehrfachnutzung
verschieben" bereits vorab; Iteration-2-Reviewer-Befund zieht dies nach).

`build_db_url` (S-054, Depot-Dashboard, `docs/specs/depot.md` AC11) zieht
die bislang nur in `app.db.migrations.env` implementierte DB-URL-Bildung
(.env.db-Konvention, `DB_*`/`POSTGRES_*`-Env-Vars) hierher, da jetzt ein
zweiter Konsument (`app.db.session`, App-Runtime-Engine für FastAPI)
dieselbe Logik braucht — analog zur `als_utc_naiv`-Verschiebung oben
("bei Mehrfachnutzung verschieben").
"""

from __future__ import annotations

import os
from datetime import UTC, datetime


def build_db_url() -> str:
    """Baut die DB-URL aus DB_*/POSTGRES_*-Env-Vars (.env.db-Konvention,
    security/R01: keine Klartext-Credentials im Repo).

    Liest wahlweise die generischen `DB_*`-Namen oder die Compose-Konvention
    `POSTGRES_*` (siehe `.env.db.example`). Fehlt eine Pflicht-Variable in
    beiden Namensschemata, bricht der Aufruf mit Nennung der fehlenden
    Variable ab (kein stiller Fallback auf Default-Credentials)."""
    name = os.environ.get("DB_NAME") or os.environ.get("POSTGRES_DB")
    user = os.environ.get("DB_USER") or os.environ.get("POSTGRES_USER")
    password = os.environ.get("DB_PASSWORD") or os.environ.get("POSTGRES_PASSWORD")
    host = os.environ.get("DB_HOST", "localhost")
    port = os.environ.get("DB_PORT", "5432")

    missing = [
        env_names
        for value, env_names in (
            (name, "DB_NAME/POSTGRES_DB"),
            (user, "DB_USER/POSTGRES_USER"),
            (password, "DB_PASSWORD/POSTGRES_PASSWORD"),
        )
        if not value
    ]
    if missing:
        raise RuntimeError(
            "Fehlende DB-Umgebungsvariable(n): "
            + ", ".join(missing)
            + " — bitte .env.db setzen (siehe .env.db.example)."
        )

    return f"postgresql+psycopg://{user}:{password}@{host}:{port}/{name}"


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
