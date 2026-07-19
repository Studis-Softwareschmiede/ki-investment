"""Demo-/Seed-Modus — Einstiegspunkt (Story S-070,
`docs/specs/frontend-cockpit.md` AC22).

**Env-Gate (AC22 "env-gated über `SEED_DEMO`, default aus"):**
`ist_demo_seed_aktiv()` liest die Umgebungsvariable `SEED_DEMO` direkt
(nicht über `app.config.Settings`/`pydantic-settings`, da dies keine
laufzeit-relevante App-Konfiguration ist, sondern ein einmaliger
Start-Schalter für einen expliziten CLI-Aufruf) — jeder Wahrheits-Wert
(`"1"`, `"true"`, `"yes"`, gross-/kleinschreibungsunabhängig) aktiviert
den Seed, alles andere (inkl. fehlender Variable) lässt ihn inaktiv.
Ohne gesetztes `SEED_DEMO` ist `run()` ein No-Op — ein produktiver Start
(Docker-Entrypoint, Migrations-Job, App-Server) seedet dadurch NIE
versehentlich (AC22-Kern-Invariante "Produktion seedet nie versehentlich").

**Aufruf-Muster (robustestes von zwei laut Task-Vorgabe zulässigen
Mustern):** eigenständiges, explizit aufzurufendes Skript
(`uv run python -m app.demo.seed`, `SEED_DEMO=1` gesetzt) statt eines
FastAPI-Startup-Hooks in `app/main.py` — vermeidet den in der aktuellen
Board-Iteration aktiven `app/main.py`-Hot-Spot (vier parallele Stories)
vollständig UND verhindert, dass ein versehentlich gesetztes `SEED_DEMO`
bei JEDEM Prozessstart (App-Server, Test-Worker, Migrations-Job) seedet —
der Seed läuft nur, wenn er explizit als eigener Prozessschritt
aufgerufen wird (z. B. im Docker-Entrypoint NACH den Migrationen, VOR dem
App-Start, nur im Demo-/Preview-Deployment).

**Reihenfolge (Fremdschlüssel-Abhängigkeiten):** Instrumente zuerst
(`app.demo.instrumente`, von Depot, Kandidaten UND Warteliste referenziert
— S-079/AC28), danach Marktdaten/Depot/Kandidaten/Gate-Ampel/Warteliste
unabhängig voneinander.

**S-080 (AC31, additiv):** `app.demo.entscheide.seed_entscheide` hängt
sich unbedingt in diese Reihenfolge (nach Instrumente, unabhängig von den
übrigen Schritten) — die Feature-Gate-Prüfung (`HYBRID_BESTAETIGUNG
_AKTIV`) liegt bewusst INNERHALB des Moduls (No-Op, wenn aus), damit
dieser Hook ein unbedingter Ein-Zeiler bleibt (Hot-Spot-Minimalität)."""

from __future__ import annotations

import os
import sys

from sqlalchemy.orm import Session

from app.db.session import get_engine
from app.demo.depot import seed_depot
from app.demo.entscheide import seed_entscheide
from app.demo.instrumente import seed_instrumente
from app.demo.kandidaten import seed_kandidaten
from app.demo.lernschleife import seed_gate_ampel
from app.demo.marktdaten import seed_marktdaten
from app.demo.warteliste import seed_warteliste

_WAHR_WERTE = frozenset({"1", "true", "yes"})


def ist_demo_seed_aktiv(env: dict[str, str] | None = None) -> bool:
    """AC22: `SEED_DEMO` env-gated, Default AUS. `env=None` liest
    `os.environ` (Produktionsverhalten); ein injizierbares Mapping
    erlaubt deterministische Tests ohne echte Prozessumgebung zu
    verändern."""
    quelle = env if env is not None else os.environ
    wert = quelle.get("SEED_DEMO", "")
    return wert.strip().lower() in _WAHR_WERTE


def seed_demo_data(session: Session) -> None:
    """Führt alle Demo-Seed-Schritte in Fremdschlüssel-sicherer Reihenfolge
    aus — jeder Schritt ist für sich idempotent (siehe die jeweiligen
    Modul-Docstrings)."""
    seed_instrumente(session)
    seed_marktdaten(session)
    seed_depot(session)
    seed_kandidaten(session)
    seed_gate_ampel(session)
    seed_warteliste(session)
    seed_entscheide(session)


def run() -> None:
    """No-Op, solange `SEED_DEMO` nicht gesetzt ist (AC22)."""
    if not ist_demo_seed_aktiv():
        print("SEED_DEMO nicht gesetzt — Demo-Seed übersprungen.", file=sys.stderr)
        return

    with Session(get_engine()) as session:
        seed_demo_data(session)
    print("Demo-Seed abgeschlossen (mode=simuliert).", file=sys.stderr)


if __name__ == "__main__":
    run()
