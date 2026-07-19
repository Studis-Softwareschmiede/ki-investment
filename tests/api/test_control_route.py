"""Tests für die Control-Plane-Endpunkte `app/api/control.py` (Story S-074,
`docs/specs/frontend-cockpit.md` AC20/AC21; Story S-076 ergänzt das
`hat_offene_positionen`-Feld im Toggle-Response-Body, AC18; Story S-080
ergänzt die Entscheid-POSTs, AC30/AC31).

Covers (frontend-cockpit): AC20, AC21, AC18 (Response-Feld
`hat_offene_positionen`), AC30, AC31

HTTP-/Router-Ebenen-Test (coder/R06): deckt den vollen Pfad
Request→Router→Response-Body für `POST /api/control/anlageklassen/
{id}/toggle`, `POST /api/control/modus`, `POST /api/control/
kill-switch/ausloesen`/`freigeben` und (S-080) `POST /api/control/
entscheide/{id}/bestaetigen`/`.../ablehnen` ab (Status-Code + Body-Shape).
ALLE Routen brauchen seit dem Review-Fix (Iteration 2, AC20-HTMX-Partial)
eine DB-Session (`GateErgebnisRepository` für das Statusleisten-Rendering)
— jeder Test nutzt deshalb eine echte In-Memory-SQLite-Session (via
`app.dependency_overrides[get_session]`, analog `tests/db/
test_asset_classes.py`), auch die zuvor DB-freien Modus-/Kill-Switch-
Routen.

Deckt: Toggle-Happy-Path + 404 (unbekannte Klasse) + 422 (Klasse
ausserhalb 1..11); Modus-Override global + je Anlageklasse + 409
(`modus="echt"`, BR-019 MVP-Sperre, → AC21); Kill-Switch Auslösen +
Freigeben (→ BR-021) inkl. 422 bei leerem Grund; **Review-Fix Iteration 2
(AC20):** JEDE der drei Aktionen liefert bei `HX-Request: true` UND
Erfolg das gerenderte Status-Partial (HTML, `data-testid`-Anker aus
`partials/statusleiste.html`) statt JSON — ohne den Header bzw. bei
einem Fehlerfall (404) bleibt es JSON. **S-080 (AC30/AC31):** Bestätigen/
Ablehnen-Happy-Path (inkl. `entschieden_am` gesetzt) + 409 (bereits
entschieden) + 404 (unbekannte ID, ungültige UUID) + 404 bei inaktivem
Feature-Flag (AC31, auch für eine sonst gültige ID) + HTMX-Partial-
Rückgabe (`partials/entscheide-liste.html`-Anker) vs. JSON ohne Header."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.config import Settings, get_settings
from app.core import kill_switch, modus_override
from app.db.base import Base
from app.db.models import AssetClass, HybridEntscheid, Instrument
from app.db.session import get_session
from app.main import app

#: SQLite-Falle: eine rein numerische Hex-Zeichenkette (z.B.
#: "11111111-1111-...") bekommt unter SQLite NUMERIC-Spalten-Affinität
#: zugewiesen und wird beim Lesen stillschweigend zu einem Float
#: konvertiert (`AttributeError: 'float' object has no attribute
#: 'replace'`) — deshalb hier `uuid.uuid4()` statt eines lesbaren
#: Literals (Konvention von `tests/adapters/repositories/
#: test_position_repository.py`).
_TITEL_ID = str(uuid.uuid4())
_ENTSCHEID_ID = str(uuid.uuid4())


def _session_mit_anlageklassen(*eintraege: AssetClass) -> Session:
    # `check_same_thread=False` + `StaticPool` (EINE geteilte Connection):
    # `TestClient` führt synchrone Endpunkte im Threadpool aus
    # (fastapi/A03) — eine In-Memory-SQLite-Connection ohne diese beiden
    # Optionen ist ausserhalb ihres Erzeuger-Threads nicht nutzbar
    # (`sqlite3.ProgrammingError`).
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    session = Session(engine)
    for eintrag in eintraege:
        session.add(eintrag)
    session.commit()
    return session


def _client(
    session: Session | None = None, *, hybrid_bestaetigung_aktiv: bool = True
) -> TestClient:
    if session is not None:
        app.dependency_overrides[get_session] = lambda: session
    app.dependency_overrides[get_settings] = lambda: Settings(
        hybrid_bestaetigung_aktiv=hybrid_bestaetigung_aktiv
    )
    return TestClient(app)


def _session_mit_offenem_entscheid() -> Session:
    """S-080 (AC30): eine offene Hybrid-Entscheid-Zeile + zugehöriges
    `Instrument` — dasselbe In-Memory-SQLite-Muster wie
    `_session_mit_anlageklassen`."""
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    session = Session(engine)
    session.add(
        Instrument(
            id=uuid.UUID(_TITEL_ID),
            symbol="ROG",
            name="Roche Holding AG",
            asset_class_id=1,
            currency="CHF",
        )
    )
    session.add(
        HybridEntscheid(
            id=uuid.UUID(_ENTSCHEID_ID),
            instrument_id=uuid.UUID(_TITEL_ID),
            richtung="kauf",
            groesse=Decimal("5"),
            vorgeschlagene_order="Market-Buy 5 Stk. Roche Holding AG",
            frist=datetime(2026, 7, 22, 16, 0, tzinfo=UTC),
            begruendung="Gesamtscore 8.5 (KAUF-Schwelle).",
            status="offen",
            mode="simuliert",
        )
    )
    session.commit()
    return session


@pytest.fixture(autouse=True)
def _zustand_isolieren():
    kill_switch.reset_fuer_tests()
    modus_override.reset_fuer_tests()
    yield
    kill_switch.reset_fuer_tests()
    modus_override.reset_fuer_tests()
    app.dependency_overrides.clear()


def test_anlageklassen_toggle_deaktiviert_und_liefert_aktualisierten_eintrag() -> None:
    """@trace frontend-cockpit#AC20 — der POST schreibt über den
    bestehenden Konfig-Schreibpfad und liefert den neuen Zustand zurück."""
    session = _session_mit_anlageklassen(
        AssetClass(id=1, name="Aktien", prio_stufe="MVP", aktiv=True)
    )
    client = _client(session)

    resp = client.post("/api/control/anlageklassen/1/toggle", json={"aktiv": False})

    assert resp.status_code == 200
    assert resp.json() == {
        "id": 1,
        "name": "Aktien",
        "aktiv": False,
        "prio_stufe": "MVP",
        "hat_offene_positionen": False,
    }


def test_anlageklassen_toggle_liefert_404_fuer_unbekannte_klasse() -> None:
    """@trace frontend-cockpit#AC20 — eine nicht existierende
    `asset_class_id` (innerhalb 1..11) liefert 404, keinen 500/leeren
    Erfolg."""
    session = _session_mit_anlageklassen()
    client = _client(session)

    resp = client.post("/api/control/anlageklassen/5/toggle", json={"aktiv": True})

    assert resp.status_code == 404


def test_anlageklassen_toggle_liefert_422_fuer_asset_class_id_ausserhalb_1_bis_11() -> None:
    """@trace frontend-cockpit#AC20 — Pfad-Validierung (Pydantic
    Path-Constraint) lehnt `asset_class_id` ausserhalb 1..11 mit 422 ab,
    bevor der Schreibpfad überhaupt erreicht wird."""
    client = _client(_session_mit_anlageklassen())

    resp = client.post("/api/control/anlageklassen/12/toggle", json={"aktiv": True})

    assert resp.status_code == 422


def test_modus_global_override_akzeptiert_simuliert() -> None:
    """@trace frontend-cockpit#AC20 — ein globaler Override auf
    `"simuliert"` (die im MVP einzig zulässige Ebene, BR-019) wird
    persistiert und zurückgegeben."""
    client = _client(_session_mit_anlageklassen())

    resp = client.post("/api/control/modus", json={"modus": "simuliert"})

    assert resp.status_code == 200
    assert resp.json()["global_modus"] == "simuliert"


def test_modus_override_je_anlageklasse_akzeptiert_simuliert() -> None:
    """@trace frontend-cockpit#AC20 — BR-019 "je Klasse überschreibbar":
    ein Anlageklassen-spezifischer Override wird gesetzt."""
    client = _client(_session_mit_anlageklassen())

    resp = client.post("/api/control/modus", json={"modus": "simuliert", "asset_class_id": 7})

    assert resp.status_code == 200
    assert resp.json()["modus_je_anlageklasse"] == {"7": "simuliert"}


def test_modus_echt_wird_mit_409_abgelehnt_mvp_live_sperre() -> None:
    """@trace frontend-cockpit#AC21 — die MVP-Live-Sperre (BR-019) lehnt
    `modus="echt"` mit 409 (Zustandsmaschinen-Verstoss) ab, NICHT mit
    einem generischen 422/500."""
    client = _client(_session_mit_anlageklassen())

    resp = client.post("/api/control/modus", json={"modus": "echt"})

    assert resp.status_code == 409


def test_modus_echt_je_anlageklasse_wird_ebenfalls_mit_409_abgelehnt() -> None:
    """@trace frontend-cockpit#AC21 — dieselbe MVP-Sperre gilt für den
    je-Anlageklasse-Override, nicht nur den globalen."""
    client = _client(_session_mit_anlageklassen())

    resp = client.post("/api/control/modus", json={"modus": "echt", "asset_class_id": 3})

    assert resp.status_code == 409


def test_kill_switch_ausloesen_setzt_zustand_angehalten() -> None:
    """@trace frontend-cockpit#AC20 — löst den bestehenden Kill-Switch
    (→ BR-021) manuell aus und liefert den neuen Status."""
    client = _client(_session_mit_anlageklassen())

    resp = client.post(
        "/api/control/kill-switch/ausloesen", json={"grund": "Owner hat Notaus gedrückt"}
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body["zustand"] == "angehalten"
    assert body["quelle"] == "manuell"
    assert body["grund"] == "Owner hat Notaus gedrückt"


def test_kill_switch_ausloesen_lehnt_leeren_grund_ab() -> None:
    """@trace frontend-cockpit#AC20 — ein leerer Grund verletzt das
    AC11-Protokoll (Pflichtfeld) und wird mit 422 abgelehnt."""
    client = _client(_session_mit_anlageklassen())

    resp = client.post("/api/control/kill-switch/ausloesen", json={"grund": ""})

    assert resp.status_code == 422


def test_kill_switch_freigeben_setzt_zustand_normal() -> None:
    """@trace frontend-cockpit#AC20/AC21 — die separate Freigabe-Aktion
    (→ BR-021/AC3, `HALTED → NORMAL`) setzt den Kill-Switch manuell
    zurück."""
    client = _client(_session_mit_anlageklassen())
    client.post("/api/control/kill-switch/ausloesen", json={"grund": "Test-Auslösung"})

    resp = client.post("/api/control/kill-switch/freigeben")

    assert resp.status_code == 200
    body = resp.json()
    assert body["zustand"] == "normal"
    assert body["quelle"] is None


def test_anlageklassen_toggle_htmx_liefert_gerendertes_statusleisten_partial() -> None:
    """@trace frontend-cockpit#AC20 — bei `HX-Request: true` UND Erfolg
    liefert der Toggle-POST die gerenderte Statusleiste (HTML,
    `statusleiste.html`-Anker) statt des JSON-`response_model`-Bodys
    (Review-Fix Iteration 2)."""
    session = _session_mit_anlageklassen(
        AssetClass(id=1, name="Aktien", prio_stufe="MVP", aktiv=True)
    )
    client = _client(session)

    resp = client.post(
        "/api/control/anlageklassen/1/toggle",
        json={"aktiv": False},
        headers={"HX-Request": "true"},
    )

    assert resp.status_code == 200
    assert "text/html" in resp.headers["content-type"]
    assert 'data-testid="ampel"' in resp.text
    assert 'data-testid="killswitch"' in resp.text
    assert 'data-testid="modus-badge"' in resp.text
    assert 'data-testid="heartbeat"' in resp.text
    assert 'data-testid="drawdown"' in resp.text
    assert 'data-testid="halluzination-kpi"' in resp.text


def test_anlageklassen_toggle_ohne_hx_header_bleibt_json() -> None:
    """@trace frontend-cockpit#AC20 — ohne `HX-Request`-Header liefert die
    Route weiterhin den bisherigen JSON-`response_model`-Body
    (Rückwärtskompatibilität, Review-Fix Iteration 2)."""
    session = _session_mit_anlageklassen(
        AssetClass(id=1, name="Aktien", prio_stufe="MVP", aktiv=True)
    )
    client = _client(session)

    resp = client.post("/api/control/anlageklassen/1/toggle", json={"aktiv": False})

    assert "application/json" in resp.headers["content-type"]
    assert resp.json() == {
        "id": 1,
        "name": "Aktien",
        "aktiv": False,
        "prio_stufe": "MVP",
        "hat_offene_positionen": False,
    }


def test_anlageklassen_toggle_404_bleibt_json_auch_mit_hx_header() -> None:
    """@trace frontend-cockpit#AC20 — ein Fehlerfall (404) liefert IMMER
    JSON, auch bei `HX-Request: true` (kein HTML-Fehlerband in diesem
    Fix, Status-Code bleibt HX-kompatibel, siehe Moduldocstring
    `app/api/control.py`)."""
    client = _client(_session_mit_anlageklassen())

    resp = client.post(
        "/api/control/anlageklassen/5/toggle",
        json={"aktiv": True},
        headers={"HX-Request": "true"},
    )

    assert resp.status_code == 404
    assert "application/json" in resp.headers["content-type"]


def test_modus_htmx_liefert_gerendertes_statusleisten_partial() -> None:
    """@trace frontend-cockpit#AC20 — der Modus-POST liefert bei
    `HX-Request: true` UND Erfolg ebenfalls das gerenderte Status-Partial
    statt JSON; der (weiterhin gesperrte) Modus-Badge zeigt SIMULIERT."""
    client = _client(_session_mit_anlageklassen())

    resp = client.post(
        "/api/control/modus", json={"modus": "simuliert"}, headers={"HX-Request": "true"}
    )

    assert resp.status_code == 200
    assert "text/html" in resp.headers["content-type"]
    assert 'data-testid="modus-badge"' in resp.text
    assert 'data-modus="simuliert"' in resp.text


def test_modus_409_bleibt_json_auch_mit_hx_header() -> None:
    """@trace frontend-cockpit#AC21 — die MVP-Live-Sperre (409) bleibt
    auch bei `HX-Request: true` eine JSON-Fehlerantwort."""
    client = _client(_session_mit_anlageklassen())

    resp = client.post("/api/control/modus", json={"modus": "echt"}, headers={"HX-Request": "true"})

    assert resp.status_code == 409
    assert "application/json" in resp.headers["content-type"]


def test_kill_switch_ausloesen_htmx_liefert_partial_mit_aktualisiertem_zustand() -> None:
    """@trace frontend-cockpit#AC20/AC21 — nach der Auslösung zeigt das
    per HTMX zurückgelieferte Partial den neuen Kill-Switch-Zustand
    (`angehalten`/„HALTED") — belegt, dass das Partial tatsächlich
    aktualisierte Daten trägt, nicht nur irgendein Template."""
    client = _client(_session_mit_anlageklassen())

    resp = client.post(
        "/api/control/kill-switch/ausloesen",
        json={"grund": "Owner hat Notaus gedrückt"},
        headers={"HX-Request": "true"},
    )

    assert resp.status_code == 200
    assert "text/html" in resp.headers["content-type"]
    assert 'data-betriebszustand="angehalten"' in resp.text
    assert "HALTED" in resp.text


def test_kill_switch_freigeben_htmx_liefert_partial_mit_normal_zustand() -> None:
    """@trace frontend-cockpit#AC20/AC21 — nach der Freigabe zeigt das
    Partial wieder den Normalzustand."""
    session = _session_mit_anlageklassen()
    client = _client(session)
    client.post("/api/control/kill-switch/ausloesen", json={"grund": "Test-Auslösung"})

    resp = client.post("/api/control/kill-switch/freigeben", headers={"HX-Request": "true"})

    assert resp.status_code == 200
    assert "text/html" in resp.headers["content-type"]
    assert 'data-betriebszustand="normal"' in resp.text


def test_entscheid_bestaetigen_setzt_status_und_liefert_json() -> None:
    """@trace frontend-cockpit#AC30 — Happy-Path: `offen` → `bestaetigt`,
    `entschieden_am` gesetzt, JSON ohne `HX-Request`-Header."""
    client = _client(_session_mit_offenem_entscheid())

    resp = client.post(f"/api/control/entscheide/{_ENTSCHEID_ID}/bestaetigen")

    assert resp.status_code == 200
    body = resp.json()
    assert body["entscheid_id"] == _ENTSCHEID_ID
    assert body["status"] == "bestaetigt"
    assert body["entschieden_am"] is not None


def test_entscheid_ablehnen_setzt_status_abgelehnt() -> None:
    """@trace frontend-cockpit#AC30 — Happy-Path Ablehnen."""
    client = _client(_session_mit_offenem_entscheid())

    resp = client.post(f"/api/control/entscheide/{_ENTSCHEID_ID}/ablehnen")

    assert resp.status_code == 200
    assert resp.json()["status"] == "abgelehnt"


def test_entscheid_bereits_entschieden_liefert_409() -> None:
    """@trace frontend-cockpit#AC30 — ein zweiter Bestätigen-/Ablehnen-
    Versuch auf derselben, bereits entschiedenen Zeile liefert 409
    (Zustandsmaschinen-Verstoss, analog der Modus-409-Konvention)."""
    client = _client(_session_mit_offenem_entscheid())
    client.post(f"/api/control/entscheide/{_ENTSCHEID_ID}/bestaetigen")

    resp = client.post(f"/api/control/entscheide/{_ENTSCHEID_ID}/ablehnen")

    assert resp.status_code == 409


def test_entscheid_unbekannte_id_liefert_404() -> None:
    """@trace frontend-cockpit#AC30 — eine nicht existierende (aber
    gültige) UUID liefert 404, keinen 500."""
    client = _client(_session_mit_offenem_entscheid())

    resp = client.post("/api/control/entscheide/99999999-9999-9999-9999-999999999999/bestaetigen")

    assert resp.status_code == 404


def test_entscheid_ungueltige_uuid_liefert_404() -> None:
    """@trace frontend-cockpit#AC30 — eine syntaktisch ungültige
    `entscheid_id` liefert 404, keinen 500/422-Crash."""
    client = _client(_session_mit_offenem_entscheid())

    resp = client.post("/api/control/entscheide/nicht-eine-uuid/bestaetigen")

    assert resp.status_code == 404


def test_entscheid_bestaetigen_bei_inaktivem_feature_flag_liefert_404() -> None:
    """@trace frontend-cockpit#AC31 — ist der Hybrid-Bestätigungs-Flow
    deaktiviert (Default), liefert der POST 404 — auch für eine sonst
    gültige, offene `entscheid_id` ("Control-POSTs sind inaktiv/
    gesperrt")."""
    client = _client(_session_mit_offenem_entscheid(), hybrid_bestaetigung_aktiv=False)

    resp = client.post(f"/api/control/entscheide/{_ENTSCHEID_ID}/bestaetigen")

    assert resp.status_code == 404


def test_entscheid_bestaetigen_htmx_liefert_gerendertes_entscheide_partial() -> None:
    """@trace frontend-cockpit#AC30 — bei `HX-Request: true` UND Erfolg
    liefert der POST das aktualisierte Offene-Entscheide-Partial (HTML,
    `entscheide-liste`-Anker) statt JSON; der bestätigte Entscheid
    verschwindet aus der (nur `status="offen"` zeigenden) Liste."""
    client = _client(_session_mit_offenem_entscheid())

    resp = client.post(
        f"/api/control/entscheide/{_ENTSCHEID_ID}/bestaetigen",
        headers={"HX-Request": "true"},
    )

    assert resp.status_code == 200
    assert "text/html" in resp.headers["content-type"]
    assert 'data-testid="entscheide-liste"' in resp.text
    assert 'data-testid="entscheide-empty"' in resp.text
    assert _ENTSCHEID_ID not in resp.text


def test_entscheid_409_bleibt_json_auch_mit_hx_header() -> None:
    """@trace frontend-cockpit#AC30 — die 409-Fehlerantwort (bereits
    entschieden) bleibt auch bei `HX-Request: true` JSON, analog der
    bestehenden 404/409-Konvention der übrigen Control-Routen."""
    client = _client(_session_mit_offenem_entscheid())
    client.post(f"/api/control/entscheide/{_ENTSCHEID_ID}/bestaetigen")

    resp = client.post(
        f"/api/control/entscheide/{_ENTSCHEID_ID}/ablehnen", headers={"HX-Request": "true"}
    )

    assert resp.status_code == 409
    assert "application/json" in resp.headers["content-type"]
