"""Deterministischer UUID-Namensraum für Demo-Seed-IDs (Story S-070).

Analog zum bestehenden `data_source`-Seed-Muster (Migration
`ea80c97626ee`, `uuid.uuid5` je Slug): jede Demo-Zeile bekommt eine aus
einem stabilen Slug abgeleitete `uuid.UUID` — ein wiederholter Seed-Lauf
trifft dieselbe Zeile (Existenzprüfung vor Insert), statt bei jedem Lauf
neue, zufällige IDs (und damit Duplikate) zu erzeugen."""

from __future__ import annotations

import uuid

#: Eigener Namensraum, getrennt vom `data_source`-Seed-Namensraum
#: (`app.db.migrations.versions.ea80c97626ee`) — Demo-Slugs und
#: Produktions-Seed-Slugs dürfen sich unabhängig voneinander entwickeln,
#: ohne Kollisionsrisiko.
_DEMO_NAMESPACE = uuid.uuid5(uuid.NAMESPACE_DNS, "ki-investment.demo-seed")


def demo_id(slug: str) -> uuid.UUID:
    """Deterministische `uuid.UUID` für einen Demo-Slug (idempotente
    Primärschlüssel-Vergabe)."""
    return uuid.uuid5(_DEMO_NAMESPACE, slug)
