"""Kandidatensuche-Domäne (Story S-029, Spec `docs/specs/kandidatensuche.md`,
Modul 3 "Suchkriteria", architecture.md §3 — Layer `domain`).

Reiner Domain-Kern (architecture.md §4 P1/P3): kein I/O, kein SQLAlchemy,
keine `app.config`-Imports — Konfigurationswerte (Settings) werden vom
jeweiligen Aufrufer explizit als Parameter übergeben (Muster von
`app.domain.portfolio.position_booking.verbuche_fill`)."""

from __future__ import annotations
