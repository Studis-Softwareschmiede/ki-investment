## S-009 — Score-Engine-Kern (Done, PR #14)
- Gebaut: `app/domain/scoring/score_engine.py` (`berechne_kategorie_score`, `berechne_gesamtscore`) + Pydantic-Contracts in `app/contracts/analyse_framework.py` (`MethodeEingabe` u.a.).
- Kategorie-Score: Ranking-gewichtetes Mittel NUR über vorhandene Methodenscores (AC9); Kategorie ganz ohne Scores → `None` (Vorbereitung AC8, nicht 0). Gesamtscore: `Σ(Kat-Score×Gewicht)/100`, fehlende Kategorie → `ValueError`.
- Für S-010 (Signal/Schwellen/Sanity-Cap): auf `berechne_gesamtscore` aufsetzen; Kategorie-Scores für Risiko-Cap (AC7) liegen einzeln vor. Ranking strukturell 1–10 (Pydantic), Methodenscore außerhalb 1–10 wird ausgeschlossen statt abgelehnt.
- Fallstrick: Spec-AC4-Zwischensumme wurde in PR #14 präzisiert (131→151, Ergebnis 6.86 unverändert) — Spec ist aktuell, nicht „korrigieren".
