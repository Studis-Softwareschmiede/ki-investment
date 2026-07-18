"""Ampel-Ableitung & Regel-Promotion (Story S-062, Spec
`docs/specs/lernschleife.md` AC10/AC11/AC12, → BR-119).

Reiner Domain-Kern (architecture.md §4 P1): keine I/O, keine DB, kein LLM.
Verdrahtet die bereits vorliegenden Stufe-A-/Stufe-B-Reports (S-060/S-061)
zur Ampel (AC10) und übergibt eine Ampel-Entscheidung AUSSCHLIESSLICH über
`app.domain.kandidatensuche.regel_governance.uebernehme_regelaenderung`
(S-057, die einzige dafür vorgesehene Stelle) an die Suchkriteria (AC11).

- **AC10 (Ampel):** `leite_ampel_ab` bildet `StufeAReport.ergebnis` +
  (optional) `StufeBReport.psr_bestanden` auf GENAU einen Ampel-Status ab
  — deckungsgleich mit BR-119 ("🟢 nur wenn Stufe A **und** B bestanden
  (sample ≥ 100, WFE ≥ 0.5, PSR ≥ 0.95); 🟡 A ok/B läuft; 🔴
  durchgefallen"):
  - `stufe_a.ergebnis == "nicht_bewertet"` (AC4/A3, Stichprobe unter der
    Bewertungsuntergrenze) → `None`: **kein Urteil, keine Ampel** — A3
    ist laut Spec ausdrücklich kein Ampel-Zustand ("gar nicht bewertet",
    "kein Urteil, keine Übernahme"), sondern liegt ausserhalb der drei
    🟢/🟡/🔴-Zustände, die AC10 aufzählt.
  - `stufe_a.ergebnis == "durchgefallen"` → `"rot"` (deckt A2).
  - `stufe_a.ergebnis == "bestanden"` und `stufe_b is None` → `"gelb"`
    (deckt A1 — Stufe A bestanden, Stufe B läuft noch mit).
  - `stufe_a.ergebnis == "bestanden"` und `stufe_b.psr_bestanden` →
    `"gruen"` (beide Stufen bestanden).
  - `stufe_a.ergebnis == "bestanden"` und `not stufe_b.psr_bestanden` →
    `"rot"` (Stufe B nicht bestanden, AC8/A2).
- **AC11 (Promotion nur bei Grün):**
  `wende_gate_ergebnis_auf_suchkriteria_an` ist der EINZIGE hier
  vorgesehene Weg von einer abgeleiteten Ampel zu einer aktualisierten
  `SuchprofilRegistry` — er baut einen `Regelvorschlag` und reicht ihn
  ausschliesslich an `uebernehme_regelaenderung` (S-057) weiter, die
  selbst nur bei `ampel == "gruen"` übernimmt (weder Research noch das
  Gate umgehen diesen Pfad). Bei `ampel is None` (kein Urteil, AC4/A3)
  wird gar nicht erst ein `Regelvorschlag` gebaut — `Regelvorschlag.ampel`
  kennt ohnehin keinen "kein Urteil"-Wert — die Registry bleibt
  unverändert.
- **AC12 (konfigurierbare Schwellen):** keine NEUEN Schwellen — die
  Ampel-Kriterien sind bereits vollständig über `StufeAKonfiguration`
  (`mindest_stichprobe`, `bewertungsuntergrenze`, `wfe_schwelle`) und
  `StufeBKonfiguration` (`psr_schwelle`) konfigurierbar (S-060/S-061, dort
  bereits AC12-konform umgesetzt); diese Ableitung liest nur die daraus
  resultierenden Bestehen-Flags (`ergebnis`/`psr_bestanden`) und führt
  selbst keinen eigenen Zahlenvergleich gegen eine Schwelle durch.
"""

from __future__ import annotations

from app.contracts.kandidatensuche import Ampel, Regelvorschlag, Suchprofil, SuchprofilRegistry
from app.contracts.lernschleife import StufeAReport, StufeBReport
from app.domain.kandidatensuche.regel_governance import uebernehme_regelaenderung


def leite_ampel_ab(stufe_a: StufeAReport, stufe_b: StufeBReport | None = None) -> Ampel | None:
    """AC10 — siehe Modul-Docstring für die volle Fallunterscheidung.
    Liefert `None`, wenn die Hypothese laut AC4/A3 gar nicht bewertet
    wurde (kein Urteil, keine Ampel)."""
    if stufe_a.ergebnis == "nicht_bewertet":
        return None
    if stufe_a.ergebnis == "durchgefallen":
        return "rot"
    if stufe_b is None:
        return "gelb"
    return "gruen" if stufe_b.psr_bestanden else "rot"


def wende_gate_ergebnis_auf_suchkriteria_an(
    registry: SuchprofilRegistry,
    *,
    ampel: Ampel | None,
    profil: Suchprofil,
) -> SuchprofilRegistry:
    """AC11 — übergibt `profil` NUR über `uebernehme_regelaenderung` an die
    Suchkriteria (die einzige vorgesehene Übernahme-Stelle, S-057); ohne
    Ampel-Wert (`None`, AC4/A3 "kein Urteil") bleibt die Registry
    unverändert (kein `Regelvorschlag`, keine Ampel zu prüfen)."""
    if ampel is None:
        return registry
    vorschlag = Regelvorschlag(profil=profil, ampel=ampel)
    return uebernehme_regelaenderung(registry, vorschlag)


__all__ = ["leite_ampel_ab", "wende_gate_ergebnis_auf_suchkriteria_an"]
