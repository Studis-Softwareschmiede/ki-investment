"""Query-Funktion Offene-Entscheide-View (`docs/specs/frontend-cockpit.md`
AC29/AC31, Story S-080; siehe `app/api/queries/__init__.py`-Konvention).

**AC29 — Read-Modell-Gap geschlossen:** liest ausschliesslich über den
`app.domain.hybrid_entscheidung.ports.HybridEntscheidungRepository`-Port
(kein `sqlalchemy`-Import, kein `session.add`/`commit`, `tests/
architecture/test_ui_boundary.py` erzwingt das statisch).

**AC31 — Feature-Gate:** `feature_aktiv` ist ein vom Aufrufer (Router,
liest `app.config.Settings.hybrid_bestaetigung_aktiv`) injizierter
Parameter, keine eigene Konfig-Abfrage dieser Funktion — ist er `False`,
liefert diese Query-Funktion IMMER eine leere Liste, OHNE das Repository
überhaupt zu befragen: die "Default aus"-Invariante gilt unabhängig vom
tatsächlichen DB-Inhalt (auch falls dort — z. B. durch einen späteren
Flag-Wechsel — bereits Zeilen existieren).

Wird sowohl von der JSON-Route (`app.api.entscheide`) als auch von der
HTML-View (`app.api.ui.entscheide_view`) konsumiert (AC1/AC10, P4/DRY)."""

from __future__ import annotations

from app.contracts.entscheide import OffeneEntscheideResponse, OffenerEntscheidResponse
from app.domain.hybrid_entscheidung.ports import HybridEntscheidungRepository


def offene_entscheide_uebersicht(
    repository: HybridEntscheidungRepository, *, feature_aktiv: bool
) -> OffeneEntscheideResponse:
    """AC29: liefert die offenen, bestätigungspflichtigen Hybrid-Entscheide.
    AC31: `feature_aktiv=False` → immer leere Liste (Repository wird nicht
    aufgerufen)."""
    if not feature_aktiv:
        return OffeneEntscheideResponse(feature_aktiv=False, entscheide=[])
    eintraege = repository.offene_entscheide()
    return OffeneEntscheideResponse(
        feature_aktiv=True,
        entscheide=[
            OffenerEntscheidResponse(
                entscheid_id=eintrag.entscheid_id,
                titel_id=eintrag.titel_id,
                titel=eintrag.titel,
                name=eintrag.name,
                richtung=eintrag.richtung,
                groesse=eintrag.groesse,
                vorgeschlagene_order=eintrag.vorgeschlagene_order,
                frist=eintrag.frist,
                begruendung=eintrag.begruendung,
                erstellt_am=eintrag.erstellt_am,
            )
            for eintrag in eintraege
        ],
    )
