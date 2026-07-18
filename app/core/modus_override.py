"""Modus-Override-Store — der Schreibpfad hinter `POST /api/control/modus`
(Story S-074, Spec `docs/specs/frontend-cockpit.md` AC20/AC21; BR-019).

Cross-Cutting-Betriebszustand in `app/core/` (architecture.md §4: "core/
QUERSCHNITT: kill_switch, heartbeat, drawdown_monitor, secrets, logging,
errors"), analog zu `app.core.kill_switch` (S-007): ein In-Prozess,
thread-sicherer Store (kein DB-Zugriff — dieselbe "Betriebszustand statt
Konfigurationsdaten"-Konvention wie beim Kill-Switch, siehe dortiger
Modul-Docstring).

**Cold-Start-Lücke geschlossen (AC8-Docstring, `app.contracts.system_status
.SystemStatusResponse`):** `app.api.queries.system_status
.system_status_uebersicht` (S-068) baute den Modus mangels Override-Store
bislang aus einer frisch konstruierten `ModusKonfiguration()` (immer
Default `"simuliert"`, kein Override möglich) — dieser Store ist die von
jenem Docstring benannte künftige Schreibgegenseite (S-074); die Query
liest ab jetzt `aktuelle_konfiguration()` statt eines hartkodierten
Defaults, sonst wäre ein Modus-Wechsel-POST unbeobachtbar (kein Control-
Eingriff ohne sichtbare Wirkung).

**MVP-Sperre (AC21, BR-019, fail-closed, S-047-Zustandslogik wiederverwendet
statt dupliziert):** JEDER Schreibversuch validiert zuerst über die
bestehende `app.domain.execution.order_ausfuehrung.bestimme_wirksamen_modus`
(Allowlist: ausschliesslich `"simuliert"` wird durchgelassen) — jeder
andere Wert (insb. `"echt"`) wirft `LiveModusGesperrtError`, BEVOR
irgendein Zustand verändert wird (kein Teil-Schreiben bei Ablehnung)."""

from __future__ import annotations

import threading

from app.contracts.ausfuehrung_paper import ModusKonfiguration
from app.contracts.depot import Modus
from app.domain.execution.order_ausfuehrung import bestimme_wirksamen_modus

_lock = threading.Lock()
_global_modus: Modus = "simuliert"
_overrides_je_anlageklasse: dict[int, Modus] = {}


def setze_global_override(modus: Modus) -> ModusKonfiguration:
    """AC20/AC21: setzt den globalen Modus-Override. Validiert zuerst über
    `bestimme_wirksamen_modus` (BR-019-Allowlist) — bei Ablehnung
    (`LiveModusGesperrtError`) bleibt der bisherige Zustand unverändert."""
    with _lock:
        bestimme_wirksamen_modus(1, konfiguration=ModusKonfiguration(global_modus=modus))
        global _global_modus
        _global_modus = modus
        return _aktuelle_konfiguration_unlocked()


def setze_override_fuer_anlageklasse(asset_class_id: int, modus: Modus) -> ModusKonfiguration:
    """AC20/AC21 (Spec A1 "je Klasse überschreibbar"): setzt einen
    Modus-Override für GENAU diese Anlageklasse. Validiert zuerst über
    `bestimme_wirksamen_modus` (BR-019-Allowlist) — bei Ablehnung
    (`LiveModusGesperrtError`) bleibt der bisherige Zustand unverändert."""
    with _lock:
        bestimme_wirksamen_modus(
            asset_class_id,
            konfiguration=ModusKonfiguration(modus_je_anlageklasse={asset_class_id: modus}),
        )
        _overrides_je_anlageklasse[asset_class_id] = modus
        return _aktuelle_konfiguration_unlocked()


def aktuelle_konfiguration() -> ModusKonfiguration:
    """Reine Zustandsabfrage — verändert nichts (konsumiert von
    `app.api.queries.system_status`, AC8)."""
    with _lock:
        return _aktuelle_konfiguration_unlocked()


def reset_fuer_tests() -> None:
    """Nur für Tests: setzt den Store vollständig auf den MVP-Default
    zurück (global `"simuliert"`, keine Overrides)."""
    global _global_modus
    with _lock:
        _global_modus = "simuliert"
        _overrides_je_anlageklasse.clear()


def _aktuelle_konfiguration_unlocked() -> ModusKonfiguration:
    return ModusKonfiguration(
        global_modus=_global_modus,
        modus_je_anlageklasse=dict(_overrides_je_anlageklasse),
    )


__all__ = [
    "aktuelle_konfiguration",
    "reset_fuer_tests",
    "setze_global_override",
    "setze_override_fuer_anlageklasse",
]
