"""Demo-Hybrid-Entscheide (Story S-080, `docs/specs/frontend-cockpit.md`
AC31): `hybrid_entscheid` (S-080-Read-Modell, AC29).

**AC31 "Bei aktivem Flag kann der Demo-Seed deterministische offene
Entscheide order-frei füllen":** anders als die übrigen `app/demo/**`
-Module ist dieser Seed-Schritt selbst feature-gated — `seed_entscheide()`
prüft `app.config.get_settings().hybrid_bestaetigung_aktiv` **intern**
(No-Op, wenn aus) statt den Aufrufer (`app.demo.seed.seed_demo_data`) mit
einer eigenen Bedingung zu belasten (Hot-Spot-Minimalität: der Hook in
`app.demo.seed` bleibt ein unbedingter Ein-Zeiler-Aufruf).

Order-frei (AC22/AC31, §13.7-6): reiner ORM-Fixture-Insert (analog
`app.demo.kandidaten`) — kein Order-/Sizing-/Risiko-/Execution-Aufruf,
`vorgeschlagene_order` ist ein Klartext-Feld, kein reales Order-Objekt.

Idempotent: `hybrid_entscheid.id` ist deterministisch aus einem Demo-Slug
abgeleitet (`app.demo._namespace.demo_id`) — ein wiederholter Aufruf
überspringt eine bereits vorhandene Zeile vollständig."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy.orm import Session

from app.config import get_settings
from app.db.models import HybridEntscheid
from app.demo._namespace import demo_id
from app.demo.instrumente import instrument_id


@dataclass(frozen=True)
class _DemoEntscheid:
    slug: str
    titel_slug: str
    richtung: str
    groesse: Decimal
    vorgeschlagene_order: str
    frist: datetime
    begruendung: str


#: Zwei offene Entscheide (Kauf ROG, Verkauf NOVN) — deterministisch,
#: order-frei (AC31, §13.7-6). `mode="simuliert"` ist der einzige laut
#: Schema (BR-141) zulässige Wert, hier nicht extra angegeben.
_DEMO_ENTSCHEIDE: tuple[_DemoEntscheid, ...] = (
    _DemoEntscheid(
        slug="demo-entscheid-kauf-rog",
        titel_slug="demo-instrument-rog",
        richtung="kauf",
        groesse=Decimal("5"),
        vorgeschlagene_order="Market-Buy 5 Stk. Roche Holding AG",
        frist=datetime(2026, 7, 20, 16, 0, tzinfo=UTC),
        begruendung=(
            "Gesamtscore 8.5 (KAUF-Schwelle), Sanity-Cap aktiv — "
            "Bestätigung empfohlen, keine automatische Ausführung."
        ),
    ),
    _DemoEntscheid(
        slug="demo-entscheid-verkauf-novn",
        titel_slug="demo-instrument-novn",
        richtung="verkauf",
        groesse=Decimal("4"),
        vorgeschlagene_order="Market-Sell 4 Stk. Novartis AG",
        frist=datetime(2026, 7, 22, 16, 0, tzinfo=UTC),
        begruendung="Soft-Exit-Signal (Teilverkauf) — Bestätigung ausstehend.",
    ),
)


def _entscheid_id(slug: str) -> uuid.UUID:
    return demo_id(slug)


def seed_entscheide(session: Session) -> None:
    """AC31: füllt `hybrid_entscheid` NUR, wenn der Feature-Flag
    (`HYBRID_BESTAETIGUNG_AKTIV`) aktiv ist — sonst No-Op (der
    Hybrid-Bestätigungs-Flow ist per Default aus, "die Liste ist leer",
    AC29). Ein Commit je Zeile (Rollback-Radius-Begrenzung, Muster von
    `app.demo.kandidaten`/`app.demo.depot`)."""
    if not get_settings().hybrid_bestaetigung_aktiv:
        return
    for eintrag in _DEMO_ENTSCHEIDE:
        entscheid_uuid = _entscheid_id(eintrag.slug)
        if session.get(HybridEntscheid, entscheid_uuid) is not None:
            continue
        session.add(
            HybridEntscheid(
                id=entscheid_uuid,
                instrument_id=instrument_id(eintrag.titel_slug),
                richtung=eintrag.richtung,
                groesse=eintrag.groesse,
                vorgeschlagene_order=eintrag.vorgeschlagene_order,
                frist=eintrag.frist,
                begruendung=eintrag.begruendung,
                status="offen",
                mode="simuliert",
            )
        )
        session.commit()
