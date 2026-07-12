"""Secret-Hygiene-Helfer (Querschnitt, architecture.md §4 `app/core/`: „secrets").

Adapter dürfen Credentials (API-Keys/OAuth-Tokens) nie im Klartext loggen
(AC3, `docs/specs/dateneingang.md`; security-Floor `security/R01`).
`mask_secret` ist der gemeinsame Helfer dafür.
"""

from __future__ import annotations


def mask_secret(value: str | None) -> str:
    """Maskiert ein Secret für Log-/Debug-Ausgaben — gibt NIE den Klartext zurück.

    Werte mit <= 4 Zeichen werden vollständig durch `*` ersetzt. Längere
    Werte behalten die ersten/letzten zwei Zeichen zur Wiedererkennbarkeit
    in Logs, der Rest wird maskiert. `None`/leer wird als `"<leer>"` markiert.
    """
    if not value:
        return "<leer>"
    if len(value) <= 4:
        return "*" * len(value)
    return f"{value[:2]}{'*' * (len(value) - 4)}{value[-2:]}"
