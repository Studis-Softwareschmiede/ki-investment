"""Tests für den Secret-Masking-Helfer (Story S-005).

Covers (dateneingang): AC3

`app.core.secrets.mask_secret` stellt sicher, dass Adapter Credentials nie
im Klartext loggen (AC3, security-Floor `security/R01`).
"""

from __future__ import annotations

from app.core.secrets import mask_secret


def test_masks_none_and_empty_as_placeholder() -> None:
    """@trace dateneingang#AC3 — fehlender/leerer Wert wird als Platzhalter
    markiert, nie als leerer String zurückgegeben, der mit einem echten
    leeren Secret verwechselt werden könnte."""
    assert mask_secret(None) == "<leer>"
    assert mask_secret("") == "<leer>"


def test_masks_short_secret_completely() -> None:
    """@trace dateneingang#AC3 — sehr kurze Secrets (<= 4 Zeichen) werden
    vollständig maskiert, kein Zeichen bleibt erkennbar."""
    assert mask_secret("ab12") == "****"


def test_masks_long_secret_keeping_only_first_and_last_two_chars() -> None:
    """@trace dateneingang#AC3 — längere Secrets behalten nur die ersten/
    letzten zwei Zeichen, der Rest wird maskiert — das Secret selbst
    erscheint an keiner Stelle im Klartext."""
    masked = mask_secret("sk_live_ABCDEFGHIJ")
    assert masked == "sk" + "*" * 14 + "IJ"
    assert "sk_live_ABCDEFGHIJ" not in masked
