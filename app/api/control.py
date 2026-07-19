"""Control-Plane — schreibende Betriebseingriffe (Story S-074, Spec
`docs/specs/frontend-cockpit.md` AC20/AC21; architecture.md §4/§13.7
"Control-Plane (schreibend, klar getrennt)").

**AC20 Control-Boundary (Sicherheits-Invariante):** Alle drei hier
gebündelten Betriebseingriffe — Klassen-Toggle (→ BR-017/BR-018),
Modus-Schalter (→ BR-019), Kill-Switch auslösen/zurücksetzen (→ BR-021) —
laufen AUSSCHLIESSLICH über diese POSTs gegen bestehende `app/core/**`-
Zustandsfunktionen (`app.core.kill_switch`, `app.core.modus_override`,
S-047-Zustandslogik `app.domain.execution.order_ausfuehrung
.bestimme_wirksamen_modus`) bzw. den Konfig-Schreibpfad
`app.db.asset_classes.setze_toggle` — keine eigene Geschäftslogik, keine
Duplikation. Dieser Router importiert nichts aus jeder Trading-Logik
(kein Import aus `app.domain.sizing`/`app.domain.risikomanagement`, kein
Order-Erzeugungs-Aufruf) und baut selbst keine eigene Anzeige-Logik — für
das HTMX-Status-Partial (unten) liest er ausschliesslich über die
bestehende, read-only Query-Funktion `app.api.queries.system_status
.system_status_uebersicht` (P4/DRY, dieselbe Funktion, die auch
`GET /api/system/status` speist).

**Review-Fix Iteration 2 (AC20-Finding):** die POSTs lieferten zuvor
IMMER nur JSON. AC20 verlangt wörtlich: "HTMX rendert nach dem POST das
aktualisierte Status-Partial zurück (§13.7-5)." Trägt der Request den
Header `HX-Request: true` (Konvention von `htmx.org`), rendert jede Route
bei ERFOLG die bestehende Statusleiste (`partials/statusleiste.html`,
S-064-Anker) mit frischen Daten (`app.web.status_partial
.status_partial_kontext`) statt des JSON-`response_model` — ohne diesen
Header (jeder Nicht-HTMX-Aufrufer, inkl. aller bestehenden Tests) bleibt
die JSON-Antwort unverändert. Fehlerfälle (404/409/422, siehe unten)
bleiben IMMER JSON — auch bei `HX-Request: true` (Status-Code + HX-
kompatible Antwort, design.md-Fehlerzustands-Muster: ein Fehlerband im
Partial ist Sache der clientseitigen HTMX-`responseError`-Behandlung der
View-Stories S-075/S-076, kein Teil dieses Fixes).

**Jede Route trägt weiterhin `response_model`** (P2), analog zu den
bereits bestehenden Read-Routern (`app.api.config`, `app.api
.system_status`) — der JSON-Vertrag ändert sich durch den HTMX-Zweig
nicht (FastAPI validiert `response_model` nur, wenn die Funktion NICHT
bereits ein `Response`-Objekt zurückgibt).

**Fehlerfälle:** ungültige Eingaben (z. B. `asset_class_id` ausserhalb
1..11) → 422 (Pydantic-Validierung); ein per BR-019 verbotener
Zustandsübergang (`modus="echt"`) → 409 (`LiveModusGesperrtError`,
Zustandsmaschinen-Verstoss); unbekannte `asset_class_id` beim Toggle
→ 404.

**Keine Auth (MVP, §13.7):** local-only — aber ausschliesslich POSTs
(keine GET-mit-Nebenwirkung, kein CSRF-anfälliger Lesepfad).

**S-080 (AC30/AC31, additiv):** `POST /api/control/entscheide/{id}/
bestaetigen`/`.../ablehnen` — Hybrid-Entscheid bestätigen/ablehnen, das
zweite Control-Boundary-Aktionspaar dieses Moduls neben Toggle/Modus/
Kill-Switch. Schreibt ausschliesslich über `app.db.hybrid_entscheide
.entscheide` (Konfig-/Entscheid-Zustandspfad, analog `app.db
.asset_classes.setze_toggle`) — **keine** Order/Sizing/Risiko/Execution-
Auslösung (Nicht-Ziel "Keine Order-Anhalte-Mechanik", die MVP-Live-Sperre
BR-019/AC21 bleibt unangetastet: `hybrid_entscheid.mode` lässt laut
DB-CHECK strukturell nie `'echt'` zu, → BR-141). **AC31 Feature-Gate:**
ist `Settings.hybrid_bestaetigung_aktiv` aus (Default), liefern beide
Routen 404 — der Flow ist dann vollständig inaktiv/gesperrt, nicht nur
die Anzeige. Ein bereits entschiedener Entscheid (`status != "offen"`)
→ 409 (`EntscheidBereitsEntschiedenError`, Zustandsmaschinen-Verstoss,
analog `LiveModusGesperrtError`). Bei Erfolg UND `HX-Request: true`
liefert die Route das aktualisierte Offene-Entscheide-Partial (HTML,
`partials/entscheide-liste.html`) zurück, sonst den JSON-`response_model`
-Body (`EntscheidStatusResponse`) — identisches HTMX-Partial-Muster wie
die Statusleisten-Routen oben."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Path, Request, status
from sqlalchemy.orm import Session

from app.adapters.repositories.gate_result_repository import SqlAlchemyGateErgebnisRepository
from app.adapters.repositories.hybrid_entscheid_repository import (
    SqlAlchemyHybridEntscheidungRepository,
)
from app.api.queries.entscheide import offene_entscheide_uebersicht
from app.api.queries.system_status import system_status_uebersicht
from app.config import Settings, get_settings
from app.contracts.anlageklassen_config import AnlageklasseEintrag
from app.contracts.betriebssicherung import KillSwitchAusloeser, KillSwitchStatus
from app.contracts.control import (
    AnlageklassenToggleAnfrage,
    KillSwitchAusloesungsAnfrage,
    ModusKonfigurationResponse,
    ModusUeberschreibungAnfrage,
)
from app.contracts.entscheide import EntscheidStatusResponse
from app.core import kill_switch, modus_override
from app.db.asset_classes import setze_toggle
from app.db.hybrid_entscheide import EntscheidBereitsEntschiedenError, entscheide
from app.db.session import get_session
from app.domain.execution.order_ausfuehrung import LiveModusGesperrtError
from app.web.status_partial import status_partial_kontext
from app.web.templates_setup import templates

router = APIRouter(prefix="/api/control", tags=["control"])


def _ist_htmx_aufruf(request: Request) -> bool:
    """AC20: htmx.org sendet bei JEDEM HTMX-Request den Header
    `HX-Request: true` — die Namenskonvention/Prüfung entspricht der
    offiziellen htmx-Doku (Header-Wert exakt `"true"`, Gross-/
    Kleinschreibung wird von Starlette-Headern ohnehin fallunabhängig
    behandelt)."""
    return request.headers.get("HX-Request", "").lower() == "true"


def _statusleiste_partial(request: Request, session: Session) -> Any:
    """Rendert `partials/statusleiste.html` mit frischen Daten (P4/DRY,
    dieselbe Query-Funktion wie `GET /api/system/status`) — der
    Rückgabewert ist ein `Response`-Objekt, FastAPI überspringt dafür die
    `response_model`-Serialisierung der aufrufenden Route."""
    gate_ergebnis_repository = SqlAlchemyGateErgebnisRepository(session)
    aktueller_status = system_status_uebersicht(gate_ergebnis_repository=gate_ergebnis_repository)
    kontext = {"status_context": status_partial_kontext(aktueller_status)}
    return templates.TemplateResponse(request, "partials/statusleiste.html", kontext)


@router.post("/anlageklassen/{asset_class_id}/toggle", response_model=AnlageklasseEintrag)
def anlageklassen_toggle(
    request: Request,
    anfrage: AnlageklassenToggleAnfrage,
    asset_class_id: int = Path(ge=1, le=11),
    session: Session = Depends(get_session),
) -> Any:
    """AC20 (→ BR-017/BR-018): setzt den Toggle-Zustand einer Anlageklasse
    über den bestehenden Konfig-Schreibpfad `app.db.asset_classes
    .setze_toggle` — 422 bei `asset_class_id` ausserhalb 1..11 (Pydantic-
    Pfad-Constraint), 404, wenn `asset_class_id` keine bestehende Zeile
    referenziert (immer JSON, auch bei `HX-Request: true`). Bei Erfolg
    UND `HX-Request: true` liefert die Route die aktualisierte
    Statusleiste (HTML), sonst den bisherigen JSON-`response_model`-Body."""
    eintrag = setze_toggle(session, asset_class_id, anfrage.aktiv)
    if eintrag is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Anlageklasse {asset_class_id} existiert nicht.",
        )
    if _ist_htmx_aufruf(request):
        return _statusleiste_partial(request, session)
    return eintrag


@router.post("/modus", response_model=ModusKonfigurationResponse)
def modus_ueberschreiben(
    request: Request,
    anfrage: ModusUeberschreibungAnfrage,
    session: Session = Depends(get_session),
) -> Any:
    """AC20/AC21 (→ BR-019): setzt den Modus-Override global oder je
    Anlageklasse — validiert über die bestehende S-047-Zustandslogik
    (`bestimme_wirksamen_modus`, MVP-Live-Sperre, Allowlist
    fail-closed). Ein verbotener Übergang (`modus="echt"`) liefert 409,
    OHNE den bisherigen Zustand zu verändern (immer JSON, auch bei
    `HX-Request: true`). Bei Erfolg UND `HX-Request: true` liefert die
    Route die aktualisierte Statusleiste (HTML), sonst den bisherigen
    JSON-`response_model`-Body."""
    try:
        if anfrage.asset_class_id is None:
            konfiguration = modus_override.setze_global_override(anfrage.modus)
        else:
            konfiguration = modus_override.setze_override_fuer_anlageklasse(
                anfrage.asset_class_id, anfrage.modus
            )
    except LiveModusGesperrtError as fehler:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(fehler)) from fehler
    if _ist_htmx_aufruf(request):
        return _statusleiste_partial(request, session)
    return ModusKonfigurationResponse.aus_konfiguration(konfiguration)


@router.post("/kill-switch/ausloesen", response_model=KillSwitchStatus)
def kill_switch_ausloesen(
    request: Request,
    anfrage: KillSwitchAusloesungsAnfrage,
    session: Session = Depends(get_session),
) -> Any:
    """AC20/AC21 (→ BR-021): löst den Kill-Switch manuell aus
    (`app.core.kill_switch.ausloesen`) — idempotent, protokolliert JEDE
    Auslösung (S-007/S-026, unverändert). Die Bestätigungspflicht selbst
    (natives modales `<dialog>`, AC21) ist Client-seitig VOR diesem POST
    verortet (§7.11 design.md) — dieser Endpunkt setzt den bereits
    bestätigten Betriebseingriff um. Bei Erfolg UND `HX-Request: true`
    liefert die Route die aktualisierte Statusleiste (HTML), sonst den
    bisherigen JSON-`response_model`-Body."""
    ergebnis = kill_switch.ausloesen(
        KillSwitchAusloeser(quelle="manuell", zeitstempel=datetime.now(UTC), grund=anfrage.grund)
    )
    if _ist_htmx_aufruf(request):
        return _statusleiste_partial(request, session)
    return ergebnis


@router.post("/kill-switch/freigeben", response_model=KillSwitchStatus)
def kill_switch_freigeben(request: Request, session: Session = Depends(get_session)) -> Any:
    """AC20/AC21 (→ BR-021/AC3): setzt den Kill-Switch manuell zurück
    (`HALTED → NORMAL`, `app.core.kill_switch.freigeben`) — idempotent,
    ausschliesslich manuell (nie automatisch). Bei Erfolg UND
    `HX-Request: true` liefert die Route die aktualisierte Statusleiste
    (HTML), sonst den bisherigen JSON-`response_model`-Body."""
    ergebnis = kill_switch.freigeben()
    if _ist_htmx_aufruf(request):
        return _statusleiste_partial(request, session)
    return ergebnis


def _entscheide_partial(request: Request, session: Session, settings: Settings) -> Any:
    """AC30: rendert `partials/entscheide-liste.html` mit frischen Daten
    (P4/DRY, dieselbe Query-Funktion wie `GET /api/entscheide/offen`) —
    analog `_statusleiste_partial` oben."""
    repository = SqlAlchemyHybridEntscheidungRepository(session)
    daten = offene_entscheide_uebersicht(
        repository, feature_aktiv=settings.hybrid_bestaetigung_aktiv
    )
    return templates.TemplateResponse(
        request, "partials/entscheide-liste.html", {"entscheide": daten}
    )


def _entscheid_status_aendern(
    request: Request,
    entscheid_id: str,
    session: Session,
    settings: Settings,
    *,
    neuer_status: str,
) -> Any:
    """AC30/AC31: gemeinsame Implementierung von "bestätigen"/"ablehnen" —
    beide POSTs unterscheiden sich nur im Ziel-Status. AC31 Feature-Gate
    (aus) → 404, bevor überhaupt ein `entscheid_id`-Lookup versucht wird
    (der Flow ist dann vollständig inaktiv, nicht nur read-only leer)."""
    if not settings.hybrid_bestaetigung_aktiv:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Hybrid-Bestätigungs-Flow ist deaktiviert (AC31).",
        )
    try:
        zeile = entscheide(session, entscheid_id, neuer_status=neuer_status)
    except EntscheidBereitsEntschiedenError as fehler:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(fehler)) from fehler
    if zeile is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Entscheid {entscheid_id} existiert nicht oder ist nicht offen.",
        )
    if _ist_htmx_aufruf(request):
        return _entscheide_partial(request, session, settings)
    return EntscheidStatusResponse(
        entscheid_id=str(zeile.id), status=zeile.status, entschieden_am=zeile.entschieden_am
    )


@router.post("/entscheide/{entscheid_id}/bestaetigen", response_model=EntscheidStatusResponse)
def entscheid_bestaetigen(
    request: Request,
    entscheid_id: str,
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> Any:
    """AC30: bestätigt einen offenen Hybrid-Entscheid (→ `status
    ="bestaetigt"`) — löst KEINE Order aus (Nicht-Ziel "Keine
    Order-Anhalte-Mechanik"); die Bestätigungspflicht selbst (natives
    modales `<dialog>`) ist Client-seitig VOR diesem POST verortet
    (§7.11 design.md, analog `kill_switch_ausloesen` oben)."""
    return _entscheid_status_aendern(
        request, entscheid_id, session, settings, neuer_status="bestaetigt"
    )


@router.post("/entscheide/{entscheid_id}/ablehnen", response_model=EntscheidStatusResponse)
def entscheid_ablehnen(
    request: Request,
    entscheid_id: str,
    session: Session = Depends(get_session),
    settings: Settings = Depends(get_settings),
) -> Any:
    """AC30: lehnt einen offenen Hybrid-Entscheid ab (→ `status
    ="abgelehnt"`) — der Vorschlag entfällt, keine Order wird ausgelöst."""
    return _entscheid_status_aendern(
        request, entscheid_id, session, settings, neuer_status="abgelehnt"
    )
