"""Attribut-Bündel-Fixierung: annotierte Kauf-Order (Story S-040, Spec
`docs/specs/strategie-exit-regeln.md` AC1/AC11).

Reiner Domain-Kern (architecture.md §4 P1/P3): keine I/O, kein LLM, keine
DB, keine Systemzeit-Abhängigkeit im Kern (der Aufrufer kann `jetzt`
injizieren) — NFR „deterministisch und ohne LLM-Beteiligung".

- **AC1 (Main Success Scenario Schritt 5):** `fixiere_attribut_buendel()`
  fasst Ordergrösse (Position-Sizing, S-039), Strategie, Zeithorizont,
  Exit-Regeln (`ExitDefaultVorschlag`, S-038) und Kauf-These zu EINEM
  `AnnotierteKaufOrder`-Bündel zusammen, das an das Risikomanagement
  weitergereicht wird.
- **AC11:** vor der Zusammenfassung wird geprüft, ob das Bündel
  VOLLSTÄNDIG ist (Edge-Case „Fehlende oder unvollständige Exit-Regeln …
  verhindern die Weitergabe an das Risikomanagement — der Kauf wird nicht
  annotiert freigegeben"): Stop-Trigger bestimmt (nicht
  `stop_unbestimmt`, ATR-Edge-Case), Thesis-Invalidierung nicht leer, die
  Kauf-These selbst nicht leer. Fehlt eines davon, wirft die Funktion
  `UnvollstaendigesAttributBuendelError` — es entsteht KEIN
  `AnnotierteKaufOrder`.

Was dieses Modul NICHT macht: die tatsächliche DB-Persistenz von
Position/`exit_rule` (das geschieht erst, wenn die annotierte Order
tatsächlich ausgeführt wird und als `FillInput` beim Depotmodul ankommt,
siehe `app.adapters.repositories.position_repository
.SqlAlchemyPositionRepository.lege_position_an`) sowie die Cluster-
Freischaltungs-/Default-Exit-Set-Ableitungs-Prüfungen selbst (S-037/S-038,
`app.db.strategie_katalog`/`app.db.exit_regel_ableitung` — deren Ergebnis
wird hier nur noch zusammengeführt und auf Vollständigkeit geprüft)."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from app.contracts.strategie_exit_regeln import AnnotierteKaufOrder, ExitDefaultVorschlag


class UnvollstaendigesAttributBuendelError(ValueError):
    """AC11 / Edge-Case (`docs/specs/strategie-exit-regeln.md`): der
    Stop-Trigger ist unbestimmt (ATR nicht berechenbar), die Thesis-
    Invalidierung fehlt, oder die Kauf-These selbst fehlt — der Kauf wird
    NICHT annotiert an das Risikomanagement weitergegeben."""


def _ist_leer(wert: str | None) -> bool:
    """Analog zu `app.contracts.depot._ist_leer`/`app.db.exit_regel_ableitung
    ._ist_leer` — `None` oder ein reiner Whitespace-String zählt als
    „fehlend"."""
    return wert is None or wert.strip() == ""


def fixiere_attribut_buendel(
    *,
    titel_id: str,
    ordergroesse: Decimal,
    strategie: str,
    zeithorizont: int,
    exit_regeln: ExitDefaultVorschlag,
    these: str,
    jetzt: datetime | None = None,
) -> AnnotierteKaufOrder:
    """AC1/AC11: fixiert das Attribut-Bündel zu einer `AnnotierteKaufOrder`
    — vorausgesetzt, das Exit-Regel-Bündel ist vollständig (AC11).

    `strategie`/`zeithorizont` werden hier NICHT erneut gegen den Katalog/
    die Cluster-Freischaltung geprüft (S-037, `app.db.strategie_katalog
    .pruefe_kombination`) — das ist Aufgabe des vorgelagerten Aufrufs, auf
    dessen bereits validiertes Ergebnis sich diese Funktion verlässt (kein
    Doppel-Check, DRY).

    Raises:
        UnvollstaendigesAttributBuendelError: der Stop-Trigger ist
            unbestimmt (`exit_regeln.stop_unbestimmt`), die Thesis-
            Invalidierung fehlt/ist leer, oder `these` fehlt/ist leer.
    """
    if exit_regeln.stop_unbestimmt:
        raise UnvollstaendigesAttributBuendelError(
            "Exit-Regeln unvollständig: Stop-Parameter unbestimmt (ATR nicht "
            "berechenbar) — Kauf wird nicht annotiert freigegeben (AC11)."
        )
    if _ist_leer(exit_regeln.thesis_invalidierung):
        raise UnvollstaendigesAttributBuendelError(
            "Exit-Regeln unvollständig: Thesis-Invalidierung fehlt — Kauf wird "
            "nicht annotiert freigegeben (AC11)."
        )
    if _ist_leer(these):
        raise UnvollstaendigesAttributBuendelError(
            "Kauf-These fehlt — Kauf wird nicht annotiert freigegeben (AC11)."
        )

    return AnnotierteKaufOrder(
        titel_id=titel_id,
        ordergroesse=ordergroesse,
        strategie=strategie,
        zeithorizont=zeithorizont,
        exit_regeln=exit_regeln,
        these=these,
        fixiert_am=jetzt if jetzt is not None else datetime.now(UTC),
        unveraenderlich=True,
    )


__all__ = ["UnvollstaendigesAttributBuendelError", "fixiere_attribut_buendel"]
