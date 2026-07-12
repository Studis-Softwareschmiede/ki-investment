---
id: analyse-framework
title: Analyse-Framework (Score-Engine, Schwellen, Spinnennetz)
status: active
version: 1
spec_format: use-case-2.0
area: analyse
---

# Spec: Analyse-Framework (Score-Engine, Schwellen, Spinnennetz)  (`analyse-framework`)

> Konzept-Herkunft: (← C-007)

> **Schicht 3 von 3.** Testbares **Verhalten + Verträge**, sprach-/paradigma-unabhängig (Intent, keine Idiome/Klassen).
> **Source of Truth** für `coder` (baut daraus), `tester` (testet die Acceptance-Kriterien + Coverage-Gate), `reviewer` (prüft den Diff dagegen — hartes Drift-Gate).

## Zweck
Die Score-Engine bewertet einen Titel über die 5 Analysekategorien (Fundamental, Technisch, Qualitativ, Makro, Risiko & Quantitativ) zu einem Gesamtscore 0–10, leitet daraus ein Handlungssignal ab, wendet einen Risiko-Sanity-Cap an und liefert die Datenbasis für das Spinnennetzdiagramm. Fehlt für eine ganze Kategorie die Evidenz, greift No-Evidence-No-Trade und der Titel wird übersprungen.

## Main Success Scenario
1. Für einen Titel und seine Anlageklasse liegen je Analysekategorie die aktuellen Methodenscores (1–10 je Methode) sowie die klassenspezifischen Rankings und Kategoriegewichte (aus [[anlageklassen-config]]) vor.
2. Je Kategorie wird der Kategorie-Score als gewichtetes Mittel der Methodenscores über die Rankings berechnet.
3. Aus den 5 Kategorie-Scores und den Kategoriegewichten der Klasse wird der Gesamtscore berechnet.
4. Aus dem Gesamtscore wird über die Score-Schwellen das Signal (KAUF / BEOBACHTEN / HALTEN / REDUZIEREN / VERKAUF) abgeleitet.
5. Der Risiko-Sanity-Cap wird angewendet.
6. Die 5 Kategorie-Scores werden als Spinnennetz-Datenbasis (5 Achsen, 0–10) ausgegeben, optional ergänzt um den historischen Durchschnitt je Achse.

## Alternative Flows
### A1: Risiko-Sanity-Cap greift
- Ist der Kategorie-Score „Risiko & Quantitativ" < 3, wird das Gesamtsignal auf höchstens **HALTEN** gedeckelt — unabhängig vom rechnerischen Gesamtscore.

### E1: Ganze Kategorie ohne Evidenz (No-Evidence-No-Trade)
- Fehlt für eine ganze Analysekategorie **jeder** Methodenscore (keine Datengrundlage), wird der Titel übersprungen: kein Gesamtscore, kein Signal. Die Kategorie wird **nicht** geschätzt und **nicht** mit 0 eingesetzt.

### A2: Einzelne Methodenscores fehlen (Kategorie hat Evidenz)
- Fehlen innerhalb einer Kategorie nur einzelne Methodenscores, fließen ausschließlich die vorhandenen Methoden in den Kategorie-Score ein (Summierung nur über vorhandene Scores); fehlende Methoden werden nicht als 0 gewertet.

## Acceptance-Kriterien

- **AC1** — Der Kategorie-Score wird berechnet als `Σ(Methodenscore × Ranking) / Σ(Ranking)` über alle Methoden der Kategorie **mit vorhandenem Methodenscore**; das Ergebnis liegt im Bereich 0–10.
- **AC2** — Der Methodenscore ist je Analyse ein Wert im Bereich 1–10 und wird bei jeder Analyse neu vergeben; das Ranking ist der klassenspezifische, feste Gewichtungswert der Methode (Bezug aus [[anlageklassen-config]]) und ändert sich nicht je Analyse.
- **AC3** — Der Gesamtscore wird berechnet als `Σ(Kategorie-Score × Kategoriegewicht der Klasse)` über die 5 Kategorien (Kategoriegewichte aus [[anlageklassen-config]], Summe 100 %); das Ergebnis liegt im Bereich 0–10.
- **AC4** — Referenz-Verifikation der Kategorie-Score-Formel: Für Fundamental mit DCF (Methodenscore 8, Ranking 9), KGV (7, 7) und KBV (5, 6) ergibt sich `(8×9 + 7×7 + 5×6) / (9+7+6) = 131/22 = 6.86` (auf 2 Dezimalstellen).
- **AC5** — Aus dem Gesamtscore wird das Signal nach folgenden Schwellen abgeleitet: **≥ 8.0 → KAUF**, **6.0–7.9 → BEOBACHTEN**, **4.0–5.9 → HALTEN**, **2.0–3.9 → REDUZIEREN**, **< 2.0 → VERKAUF**. Die Grenzwerte sind inklusiv an der Untergrenze (z. B. Gesamtscore genau 8.0 → KAUF, genau 6.0 → BEOBACHTEN, genau 2.0 → REDUZIEREN).
- **AC6** — Die Score-Schwellen sind je Anlageklasse konfigurierbar; die in AC5 genannten Werte gelten als globale **Default-Schwellen (provisorisch)** und werden je Anlageklasse noch kalibriert. Ist keine klassenspezifische Schwelle gesetzt, greifen die Default-Werte.
- **AC7** — Risiko-Sanity-Cap: Ist der Kategorie-Score „Risiko & Quantitativ" **< 3**, wird das Gesamtsignal auf höchstens **HALTEN** begrenzt; ein rechnerisches KAUF oder BEOBACHTEN wird auf HALTEN gedeckelt, während REDUZIEREN und VERKAUF unverändert bleiben (deckt A1). Der Cap-Schwellwert 3 ist konfigurierbar.
- **AC8** — No-Evidence-No-Trade: Fehlt für eine ganze Analysekategorie jeder Methodenscore, wird der Titel übersprungen (kein Gesamtscore, kein Signal), statt die Kategorie zu schätzen oder mit 0 zu belegen (deckt E1).
- **AC9** — Fehlen innerhalb einer Kategorie nur einzelne Methodenscores (die Kategorie hat mindestens einen vorhandenen Score), fließen ausschließlich die vorhandenen Methoden in `Σ(Methodenscore × Ranking) / Σ(Ranking)` ein; fehlende Methoden werden nicht als 0 gewertet (deckt A2).
- **AC10** — Spinnennetz-Datenoutput: Für jede vollständige Analyse werden die 5 Kategorie-Scores als Achsenwerte (Skala 0–10, eine Achse je Kategorie) bereitgestellt; optional wird zusätzlich der historische Durchschnitt je Achse als zweite Datenreihe geliefert.
- **AC11** — Determinismus/Reproduzierbarkeit: Identische Eingaben (Methodenscores, Rankings, Kategoriegewichte, Schwellen) liefern identische Kategorie-Scores, identischen Gesamtscore und identisches Signal.

> **Traceability:** Jeder Test trägt das kanonische Trace-Tag `@trace analyse-framework#AC<n>[,BR-NNN]`
> gemäss `knowledge/<lang>.md` → `## Spec-Tagging`. Der `tester` rechnet das Coverage-Gate
> (jede genannte AC + jede referenzierte BR ≥ 1 deckender Test).

## Verträge

**Input (je Titel):**
`{ titel, anlageklasse: 1–11, kategorien: [ { kategorie, methoden: [ { methoden_id, ranking: 1–10, methodenscore: 1–10 | fehlt } ] } ], kategoriegewichte, score_schwellen? }`
— Rankings und Kategoriegewichte stammen aus [[anlageklassen-config]]; die Methodenscores werden je Analyse geliefert (geerdet gem. [[llm-grounding]]).

**Output:**
`{ kategorie_scores: { fundamental, technisch, qualitativ, makro, risiko: 0–10 }, gesamtscore: 0–10, signal: KAUF | BEOBACHTEN | HALTEN | REDUZIEREN | VERKAUF, sanity_cap_angewendet: bool, spinnennetz: { achsen: 5×(0–10), historischer_durchschnitt?: 5×(0–10) }, uebersprungen?: { grund: "no-evidence", kategorie } }`

**Signal-Schwellen (Default, provisorisch — je Anlageklasse kalibrierbar):**

| Gesamtscore | Signal |
|---|---|
| ≥ 8.0 | KAUF |
| 6.0 – 7.9 | BEOBACHTEN |
| 4.0 – 5.9 | HALTEN |
| 2.0 – 3.9 | REDUZIEREN |
| < 2.0 | VERKAUF |

## Edge-Cases & Fehlerverhalten
- Alle Methodenscores einer Kategorie fehlen → Titel übersprungen (AC8), kein Gesamtscore.
- Σ(Ranking) einer Kategorie mit vorhandenen Scores = 0 (theoretisch, alle Rankings 0) → Kategorie gilt als ohne verwertbare Evidenz; wie fehlende Kategorie behandeln.
- Methodenscore außerhalb 1–10 → ungültige Eingabe, wird nicht verrechnet.
- Risiko-Score < 3 bei gleichzeitig hohem Gesamtscore → Signal wird auf HALTEN gedeckelt und `sanity_cap_angewendet = true`.
- Historischer Durchschnitt nicht vorhanden (neuer Titel) → Spinnennetz nur mit aktueller Datenreihe.

## NFRs
- Score-Berechnung ist rein deterministisch (keine LLM-Beteiligung an der Berechnung selbst; die Score-Erzeugung unterliegt [[llm-grounding]]).
- Kategorie-Scores und Gesamtscore auf definierte Präzision reproduzierbar (2 Dezimalstellen).

## Nicht-Ziele
- Keine Definition der Methodentabellen/Rankings/Gewichte selbst (→ [[anlageklassen-config]]).
- Keine Signal-Aggregation der Rohdaten (z-Scores, Sentiment-Decay) — das ist Sache der Datenzuführung (Konzept C-007, provisorisch, eigene Spec).
- Keine Buy-/Sell-Entscheidung, kein Sizing und keine Order (nachgelagerte Module).

## Abhängigkeiten
- [[anlageklassen-config]] — liefert Kategoriegewichte und Methoden-Rankings je Klasse.
- [[llm-grounding]] — Herkunft und Validierung der Methodenscores; No-Evidence-No-Trade als geteilte Regel.
