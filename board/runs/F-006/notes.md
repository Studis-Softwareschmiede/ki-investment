## S-009 — Score-Engine-Kern (Done, PR #14)
- Gebaut: `app/domain/scoring/score_engine.py` (`berechne_kategorie_score`, `berechne_gesamtscore`) + Pydantic-Contracts in `app/contracts/analyse_framework.py` (`MethodeEingabe` u.a.).
- Kategorie-Score: Ranking-gewichtetes Mittel NUR über vorhandene Methodenscores (AC9); Kategorie ganz ohne Scores → `None` (Vorbereitung AC8, nicht 0). Gesamtscore: `Σ(Kat-Score×Gewicht)/100`, fehlende Kategorie → `ValueError`.
- Für S-010 (Signal/Schwellen/Sanity-Cap): auf `berechne_gesamtscore` aufsetzen; Kategorie-Scores für Risiko-Cap (AC7) liegen einzeln vor. Ranking strukturell 1–10 (Pydantic), Methodenscore außerhalb 1–10 wird ausgeschlossen statt abgelehnt.
- Fallstrick: Spec-AC4-Zwischensumme wurde in PR #14 präzisiert (131→151, Ergebnis 6.86 unverändert) — Spec ist aktuell, nicht „korrigieren".

## S-010 — Signal-Ableitung, Schwellen & Sanity-Cap (Done, PR #17)
- Gebaut: `leite_signal_ab(gesamtscore, schwellen=None)` (AC5/AC6) + `wende_risiko_sanity_cap_an(signal, risiko_score, cap_schwelle=3.0)` (AC7) in `app/domain/scoring/score_engine.py`; DTOs `Signal` (Literal) + `ScoreSchwellen` (frozen, Defaults = AC5-Werte) in `app/contracts/analyse_framework.py`.
- `ScoreSchwellen` erzwingt Monotonie `kauf ≥ beobachten ≥ halten ≥ reduzieren` via `model_validator` (Reviewer-Befund Iteration 1) — inkonsistente Teil-Overrides werfen ValidationError.
- Für S-011 (AC8/AC10): Kategorie ohne Evidenz liefert weiterhin `None` aus `berechne_kategorie_score` — darauf den Skip (uebersprungen-Objekt) aufsetzen; Signal/Cap-Funktionen sind rein und wiederverwendbar für den Gesamt-Output-Vertrag.
- Cap-Grenzfall: Risiko-Score exakt 3.0 → KEIN Cap (nur < 3), getestet; Schwellen-Untergrenzen inklusiv (8.0→KAUF, 6.0→BEOBACHTEN, 2.0→REDUZIEREN).
