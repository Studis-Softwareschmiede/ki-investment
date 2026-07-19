"""Tests für die System-Status-Voll-View (`app.api.ui.system_status_view`/
`system_status_partial`), Story S-075, `docs/specs/frontend-cockpit.md`
AC17/AC19.

Covers (frontend-cockpit): AC17, AC19

HTTP-/Router-Ebenen-Test (coder/R06): deckt den vollen Pfad
Request→Router→Jinja2-Rendering→Response-Body für `GET /ui/system-status`
(volle View) **und** `GET /ui/system-status/partial` (AC19-Live-Polling-
Partial) ab — dieselbe Query-Funktion (`system_status_uebersicht`) wie
`GET /api/system/status` (`tests/api/test_system_status.py`), hier über
die vier In-Process-`app.core.**`-Zustände + einen Fake-
`GateErgebnisRepository` statt einer echten DB (analog
`tests/api/test_control_route.py`'s Zustands-Isolation).

Deckt: Ampel/Gate-Ampel mit Zeitstempel (E2-Empty-State ohne Gate-
Auswertung), Kill-Switch normal (Auslösen-Button + Bestätigungs-Dialog)
vs. angehalten (Vollbreite-Banner A1 + Freigeben-Button + Grund/Zeitpunkt),
Modus-Anzeige mit MVP-Live-Sperre sichtbar, Heartbeat JE MODUL (nicht nur
aggregiert), Drawdown-/Halluzinations-KPI-Empty-States (E2), AC19-Live-
Polling-Markup (`hx-trigger`, `aria-live`, Stale-Hinweis E1), dass die
Bestätigungs-Dialoge ausserhalb der gepollten Region liegen (kein
Fokusverlust-Risiko beim Swap), dass die persistente Shell-Statusleiste
auf dieser Seite bereits echte Werte statt des Cold-Start-Platzhalters
zeigt (AC10/P4-Wiederverwendung) sowie (Iteration 2, Review-Findings):
dass beide Kill-Switch-Dialoge bei Erfolg das `#system-status-live`-
Voll-Fragment per `htmx.ajax` sofort nachziehen (statt bis zu 8s stale
zu bleiben) UND je Dialog ein quittierbares `role="alert"`-Fehlerelement
tragen, das initial verborgen ist und dessen Sichtbarkeit über
`hx-on::before-request`/`hx-on::after-request` gesteuert wird."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from app.api.system_status import get_gate_ergebnis_repository
from app.contracts.betriebssicherung import KillSwitchAusloeser
from app.core import alerts, drawdown_monitor, hallucination_kpi, heartbeat, kill_switch
from app.domain.lernschleife.ports import LetztesGateErgebnis
from app.main import app


class _FakeGateErgebnisRepository:
    def __init__(self, ergebnis: LetztesGateErgebnis | None) -> None:
        self._ergebnis = ergebnis

    def letztes_ergebnis(self) -> LetztesGateErgebnis | None:
        return self._ergebnis


def _client(gate_ergebnis: LetztesGateErgebnis | None = None) -> TestClient:
    app.dependency_overrides[get_gate_ergebnis_repository] = lambda: _FakeGateErgebnisRepository(
        gate_ergebnis
    )
    return TestClient(app)


@pytest.fixture(autouse=True)
def _isolieren():
    kill_switch.reset_fuer_tests()
    heartbeat.reset_fuer_tests()
    drawdown_monitor.reset_fuer_tests()
    hallucination_kpi.reset_fuer_tests()
    alerts.reset_fuer_tests()
    yield
    app.dependency_overrides.clear()
    kill_switch.reset_fuer_tests()
    heartbeat.reset_fuer_tests()
    drawdown_monitor.reset_fuer_tests()
    hallucination_kpi.reset_fuer_tests()
    alerts.reset_fuer_tests()


def test_cold_start_zeigt_definierte_empty_states_ohne_null_oder_farbe() -> None:
    """E2: keine Gate-Auswertung/kein Depot-Stand/keine geprüften Analysen
    -> "—", nie 0 oder ein vorgetäuschter Farbzustand."""
    client = _client(None)

    resp = client.get("/ui/system-status")

    assert resp.status_code == 200
    html = resp.text
    assert 'data-testid="gate-ampel"' in html
    assert 'data-ampel-state="unbekannt"' in html
    assert 'data-testid="gate-ampel-zeitstempel"' in html
    assert 'data-testid="status-drawdown"' in html
    assert 'data-state="unbekannt"' in html
    assert 'data-testid="status-halluzination-kpi"' in html
    assert 'data-testid="banner"' not in html


def test_kill_switch_normal_zeigt_ausloesen_button_und_dialog() -> None:
    client = _client(None)

    html = client.get("/ui/system-status").text

    assert 'data-testid="status-killswitch"' in html
    assert 'data-betriebszustand="normal"' in html
    assert 'data-testid="killswitch-ausloesen-oeffnen"' in html
    assert 'commandfor="dialog-kill-switch-ausloesen"' in html
    assert 'data-testid="dialog-kill-switch-ausloesen"' in html
    assert 'data-testid="dialog-kill-switch-grund"' in html
    assert 'hx-ext="json-enc"' in html
    assert "/api/control/kill-switch/ausloesen" in html


def test_kill_switch_angehalten_zeigt_vollbreite_banner_und_freigeben() -> None:
    """A1: kritischer Betriebszustand -> Vollbreite-Banner mit maximaler
    Priorität, `aria-live="assertive"`, Wort statt nur Farbe (D5)."""
    zeitpunkt = datetime(2026, 7, 18, 9, 0, tzinfo=UTC)
    kill_switch.ausloesen(
        KillSwitchAusloeser(quelle="manuell", zeitstempel=zeitpunkt, grund="Testauslösung")
    )
    client = _client(None)

    html = client.get("/ui/system-status").text

    assert 'data-testid="banner"' in html
    assert 'data-severity="danger"' in html
    assert 'aria-live="assertive"' in html
    assert "HALTED" in html
    assert 'data-betriebszustand="angehalten"' in html
    assert "Testauslösung" in html
    assert 'data-testid="killswitch-freigeben-oeffnen"' in html
    assert 'commandfor="dialog-kill-switch-freigeben"' in html
    assert "/api/control/kill-switch/freigeben" in html


def test_modus_zeigt_simuliert_und_mvp_live_sperre_sichtbar() -> None:
    client = _client(None)

    html = client.get("/ui/system-status").text

    assert 'data-testid="status-modus"' in html
    assert 'data-modus="simuliert"' in html
    assert 'data-live-locked="true"' in html
    assert "SIMULIERT" in html
    assert 'data-testid="modus-live-gesperrt"' in html
    assert "BR-019" in html


def test_heartbeat_je_modul_nicht_nur_aggregiert() -> None:
    heartbeat.registriere_modul(
        "ingest", timedelta(minutes=5), jetzt=datetime.now(UTC) - timedelta(minutes=10)
    )
    heartbeat.registriere_modul("scorer", timedelta(minutes=5), jetzt=datetime.now(UTC))
    client = _client(None)

    html = client.get("/ui/system-status").text

    assert 'data-testid="heartbeat-liste"' in html
    assert html.count('data-testid="heartbeat-modul"') == 2
    assert 'data-modul-id="ingest"' in html
    assert 'data-state="ausgefallen"' in html
    assert 'data-modul-id="scorer"' in html
    assert "AUSGEFALLEN" in html


def test_keine_registrierten_module_zeigt_definierten_leerzustand() -> None:
    client = _client(None)

    html = client.get("/ui/system-status").text

    assert 'data-testid="heartbeat-leer"' in html
    assert 'data-testid="heartbeat-liste"' not in html


def test_gate_ampel_zeigt_zeitstempel_wenn_vorhanden() -> None:
    zeitpunkt = datetime(2026, 7, 15, 12, 0, tzinfo=UTC)
    client = _client(LetztesGateErgebnis(ampel="rot", ermittelt_am=zeitpunkt))

    html = client.get("/ui/system-status").text

    assert 'data-ampel-state="rot"' in html
    start = html.index('data-testid="gate-ampel-zeitstempel"')
    block = html[start : start + 200]
    assert "15.07.2026" in block


def test_live_polling_markup_ac19() -> None:
    client = _client(None)

    html = client.get("/ui/system-status").text

    assert 'data-testid="system-status-live-region"' in html
    assert 'hx-trigger="every 8s"' in html
    assert "/ui/system-status/partial" in html
    assert 'aria-live="polite"' in html
    # E1: Stale-Hinweis-Element existiert (verborgen bis ein Poll fehlschlägt).
    assert 'data-testid="system-status-stale-hinweis"' in html
    assert "hidden" in html


def test_dialoge_liegen_ausserhalb_der_gepollten_region() -> None:
    """AC19 "kein Fokusverlust": ein offener Bestätigungs-Dialog darf beim
    periodischen Poll-Swap-Ziel nicht mitgerendert (und damit zerstört)
    werden — die Dialoge liegen ausserhalb von `#system-status-live`."""
    client = _client(None)

    html = client.get("/ui/system-status").text
    live_start = html.index('id="system-status-live"')
    live_ende = html.index("</div>", live_start)
    live_block = html[live_start:live_ende]

    # Nur das öffnende `commandfor`-Attribut darf im gepollten Bereich
    # stehen (ID-Referenz) — die `<dialog>`-Definition selbst nicht.
    assert '<dialog id="dialog-kill-switch-ausloesen"' not in live_block
    assert '<dialog id="dialog-kill-switch-freigeben"' not in live_block


def test_reduced_motion_deaktiviert_animationen_global() -> None:
    """AC19: `prefers-reduced-motion` schaltet Swap-Highlights ab — über
    die bereits global in `shell.css` geltende Regel (Story S-075 fügt
    selbst keine eigene Swap-Highlight-Animation hinzu)."""
    client = _client(None)

    css = client.get("/static/css/shell.css").text

    assert "prefers-reduced-motion: reduce" in css


def test_partial_endpoint_liefert_dasselbe_datenfragment_ohne_shell() -> None:
    zeitpunkt = datetime(2026, 7, 15, 12, 0, tzinfo=UTC)
    client = _client(LetztesGateErgebnis(ampel="gruen", ermittelt_am=zeitpunkt))

    resp = client.get("/ui/system-status/partial")

    assert resp.status_code == 200
    html = resp.text
    assert 'data-testid="gate-ampel"' in html
    assert 'data-ampel-state="gruen"' in html
    # Partial ist kein Voll-Dokument (kein Shell-Rundherum, AC19 "kleine
    # Partial-Endpunkte").
    assert "<html" not in html
    assert "<nav" not in html
    # Der ÖFFNEN-Button referenziert den Dialog per `commandfor` (bleibt im
    # Partial), die `<dialog>`-Definition selbst liegt in `views/
    # system-status.html`, nicht im gepollten Fragment.
    assert 'commandfor="dialog-kill-switch-ausloesen"' in html
    assert '<dialog id="dialog-kill-switch-ausloesen"' not in html


def test_kill_switch_dialoge_aktualisieren_live_fragment_bei_erfolg() -> None:
    """Review-Finding (Iteration 1, Important): ein erfolgreicher Kill-
    Switch-POST darf nicht nur die kleine Shell-Statusleiste aktualisieren
    — das grosse `#system-status-live`-Fragment (HALTED-Banner,
    Kill-Switch-Karte) muss im selben Erfolgsfall sofort nachgezogen
    werden, statt bis zu 8s (Poll-Intervall) stale zu bleiben."""
    client = _client(None)

    html = client.get("/ui/system-status").text

    ausloesen_start = html.index('id="dialog-kill-switch-ausloesen"')
    ausloesen_ende = html.index("</dialog>", ausloesen_start)
    ausloesen_block = html[ausloesen_start:ausloesen_ende]
    assert "htmx.ajax('GET'" in ausloesen_block
    assert "/ui/system-status/partial" in ausloesen_block
    assert "target: '#system-status-live'" in ausloesen_block

    freigeben_start = html.index('id="dialog-kill-switch-freigeben"')
    freigeben_ende = html.index("</dialog>", freigeben_start)
    freigeben_block = html[freigeben_start:freigeben_ende]
    assert "htmx.ajax('GET'" in freigeben_block
    assert "/ui/system-status/partial" in freigeben_block
    assert "target: '#system-status-live'" in freigeben_block


def test_kill_switch_dialoge_haben_sichtbaren_fehlerpfad() -> None:
    """Review-Finding (Iteration 1, Important): schlägt der Kill-Switch-
    POST fehl (5xx/Netzwerkfehler), muss ein quittierbares
    `role="alert"`-Element sichtbar werden — der Dialog darf nicht
    kommentarlos offen bleiben."""
    client = _client(None)

    html = client.get("/ui/system-status").text

    ausloesen_start = html.index('id="dialog-kill-switch-ausloesen"')
    ausloesen_ende = html.index("</dialog>", ausloesen_start)
    ausloesen_block = html[ausloesen_start:ausloesen_ende]
    fehler_start = ausloesen_block.index('data-testid="dialog-kill-switch-ausloesen-fehler"')
    fehler_tag = ausloesen_block[max(0, fehler_start - 80) : fehler_start + 60]
    assert 'role="alert"' in fehler_tag
    assert "hidden" in fehler_tag
    assert "Fehler beim Auslösen" in ausloesen_block
    assert (
        "document.getElementById('dialog-kill-switch-ausloesen-fehler').hidden = true"
        in ausloesen_block
    )
    assert (
        "document.getElementById('dialog-kill-switch-ausloesen-fehler').hidden = false"
        in ausloesen_block
    )

    freigeben_start = html.index('id="dialog-kill-switch-freigeben"')
    freigeben_ende = html.index("</dialog>", freigeben_start)
    freigeben_block = html[freigeben_start:freigeben_ende]
    fehler_start = freigeben_block.index('data-testid="dialog-kill-switch-freigeben-fehler"')
    fehler_tag = freigeben_block[max(0, fehler_start - 80) : fehler_start + 60]
    assert 'role="alert"' in fehler_tag
    assert "hidden" in fehler_tag
    assert "Fehler beim Zurücksetzen" in freigeben_block
    assert (
        "document.getElementById('dialog-kill-switch-freigeben-fehler').hidden = true"
        in freigeben_block
    )
    assert (
        "document.getElementById('dialog-kill-switch-freigeben-fehler').hidden = false"
        in freigeben_block
    )


def test_statusleiste_zeigt_echte_werte_statt_cold_start_platzhalter() -> None:
    """AC17/P4-DRY: auf `/ui/system-status` speist derselbe Kontextaufbau
    auch die persistente Shell-Statusleiste (`_render(...,
    status_context=...)`) — statt des Cold-Start-Platzhalters ('unbekannt')
    zeigt sie den tatsächlichen Kill-Switch-Zustand."""
    zeitpunkt = datetime(2026, 7, 18, 9, 0, tzinfo=UTC)
    kill_switch.ausloesen(
        KillSwitchAusloeser(quelle="manuell", zeitstempel=zeitpunkt, grund="Testauslösung")
    )
    client = _client(None)

    html = client.get("/ui/system-status").text
    start = html.index('data-testid="statusleiste"')
    header_ende = html.index("</header>", start)
    header_block = html[start:header_ende]

    assert 'data-testid="killswitch"' in header_block
    assert 'data-betriebszustand="angehalten"' in header_block
