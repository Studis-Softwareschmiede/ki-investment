"""Tests für den Scheduler-Vertrag `Arbeitselement` (Story S-020).

Covers (dateneingang): AC11

`app.contracts.scheduler.Arbeitselement` ist der Modul-Vertrag Scheduler →
Queue → Worker (architecture.md §2 P2, AC11 "Jede Abfrage wird als
Arbeitselement in eine Queue-of-Work eingereiht").
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from app.contracts.scheduler import Arbeitselement


def test_versuch_defaults_to_1() -> None:
    """@trace dateneingang#AC11 — ein frisch eingereihtes Arbeitselement
    ist Versuch 1 (noch kein Retry)."""
    item = Arbeitselement(data_source_id=uuid.uuid4(), eingereiht_am=datetime.now(UTC))
    assert item.versuch == 1


def test_naechster_versuch_returns_a_new_instance_with_incremented_versuch() -> None:
    """@trace dateneingang#AC11 — `Arbeitselement` ist unveränderlich
    (`frozen=True`); ein Retry (AC10) erzeugt eine neue Instanz statt das
    bestehende Objekt zu mutieren."""
    item = Arbeitselement(data_source_id=uuid.uuid4(), eingereiht_am=datetime.now(UTC))

    retry = item.naechster_versuch()

    assert retry.versuch == 2
    assert item.versuch == 1  # Original unveraendert
    assert retry.data_source_id == item.data_source_id


def test_versuch_below_1_is_rejected() -> None:
    """@trace dateneingang#AC11 — `versuch` ist mindestens 1 (kein
    „nullter" Verarbeitungsversuch)."""
    with pytest.raises(ValidationError):
        Arbeitselement(data_source_id=uuid.uuid4(), eingereiht_am=datetime.now(UTC), versuch=0)
