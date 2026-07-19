"""Hybrid-Entscheid-Schreibpfad (Story S-080, `docs/specs/frontend-cockpit.md`
AC30) — analog `app.db.asset_classes.setze_toggle`: das einzige erlaubte
Schreib-Gegenstück zum `hybrid_entscheid`-Read-Modell (AC29), aufgerufen
ausschliesslich von den Control-POSTs `app/api/control.py` (→ AC20-Control-
Boundary, "bestätigen"/"ablehnen").

`entscheide()` setzt NUR den Status (`offen` → `bestaetigt`/`abgelehnt`) +
`entschieden_am` — es löst KEINE Order/Sizing/Risiko/Execution aus (Nicht-
Ziel "Keine Order-Anhalte-Mechanik"): die tatsächliche Order-Ausführung
eines bestätigten Entscheids bleibt laut Spec explizit post-MVP-
Backend-Scope. `mode` bleibt beim Schema-fixierten `'simuliert'`
(BR-141) — es gibt keinen Aufrufer-Pfad, der `mode` je ändert."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.db.models import HybridEntscheid

#: AC30: die beiden gültigen Ziel-Zustände eines Bestätigungs-/Ablehnungs-
#: POSTs — identisch zum DB-CHECK `ck_hybrid_entscheid_status` (ohne
#: 'offen', das ist nur der Ausgangszustand).
_NEUE_ZUSTAENDE = frozenset({"bestaetigt", "abgelehnt"})


class EntscheidBereitsEntschiedenError(Exception):
    """AC30: der Entscheid trägt bereits `status != "offen"` — kein
    erneuter Übergang zulässig (Router meldet das als 409, analog der
    bestehenden `LiveModusGesperrtError`-409-Konvention in
    `app/api/control.py`)."""

    def __init__(self, aktueller_status: str) -> None:
        self.aktueller_status = aktueller_status
        super().__init__(f"Entscheid ist bereits entschieden (status={aktueller_status!r}).")


def entscheide(session: Session, entscheid_id: str, *, neuer_status: str) -> HybridEntscheid | None:
    """AC30: setzt `HybridEntscheid.status` von `"offen"` auf
    `neuer_status` (`"bestaetigt"` oder `"abgelehnt"`) + `entschieden_am`.

    `None`, wenn `entscheid_id` keine gültige UUID ist ODER keine
    bestehende Zeile referenziert (der Router meldet das als 404, analog
    `app.db.asset_classes.setze_toggle`). Wirft
    `EntscheidBereitsEntschiedenError`, wenn die Zeile nicht mehr
    `status="offen"` ist (der Router meldet das als 409).

    **Guard gegen Lost Update (DBA-Review Iteration 2, Important):** die
    Zeile wird gesperrt gelesen (`with_for_update=True`, identische
    Konvention zu `PositionRepository.offene_positionen`) — unter Postgres
    serialisiert das zwei parallele Bestätigen-/Ablehnen-Requests auf
    Row-Lock-Ebene: der zweite Aufruf blockiert, bis der erste committet
    hat, und sieht danach den bereits geänderten `status`, wirft also
    korrekt `EntscheidBereitsEntschiedenError` statt den ersten Übergang
    kommentarlos zu überschreiben. Unter SQLite (Tests) ist `FOR UPDATE`
    wirkungslos, aber fehlerfrei (kein Zeilensperren-Support)."""
    assert neuer_status in _NEUE_ZUSTAENDE, f"unerwarteter Ziel-Status: {neuer_status!r}"
    try:
        entscheid_uuid = uuid.UUID(entscheid_id)
    except ValueError:
        return None
    zeile = session.get(HybridEntscheid, entscheid_uuid, with_for_update=True)
    if zeile is None:
        return None
    if zeile.status != "offen":
        raise EntscheidBereitsEntschiedenError(zeile.status)
    zeile.status = neuer_status
    zeile.entschieden_am = datetime.now(UTC)
    session.commit()
    session.refresh(zeile)
    return zeile


__all__ = ["EntscheidBereitsEntschiedenError", "entscheide"]
