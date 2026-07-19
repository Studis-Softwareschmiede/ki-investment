"""Tests für die Control-Plane-Endpunkte `app/api/control.py` (Story S-074,
`docs/specs/frontend-cockpit.md` AC20/AC21; Story S-076 ergänzt das
`hat_offene_positionen`-Feld im Toggle-Response-Body, AC18).

Covers (frontend-cockpit): AC20, AC21, AC18 (nur das Response-Feld
`hat_offene_positionen` am bestehenden Toggle-Endpunkt)

HTTP-/Router-Ebenen-Test (coder/R06): deckt den vollen Pfad
Request→Router→Response-Body für `POST /api/control/anlageklassen/
{id}/toggle`, `POST /api/control/modus` und `POST /api/control/
kill-switch/ausloesen`/`freigeben` ab (Status-Code + Body-Shape). ALLE
Routen brauchen seit dem Review-Fix (Iteration 2, AC20-HTMX-Partial) eine
DB-Session (`GateErgebnisRepository` für das Statusleisten-Rendering) —
jeder Test nutzt deshalb eine echte In-Memory-SQLite-Session (via
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
einem Fehlerfall (404) bleibt es JSON."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.core import kill_switch, modus_override
from app.db.base import Base
from app.db.models import AssetClass
from app.db.session import get_session
from app.main import app


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


def _client(session: Session | None = None) -> TestClient:
    if session is not None:
        app.dependency_overrides[get_session] = lambda: session
    return TestClient(app)


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
