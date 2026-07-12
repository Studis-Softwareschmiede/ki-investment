---
id: analyse-pipelines
title: Analysepfade — Einstieg (Buy) und Wiederbewertung (Sell)
status: active
version: 1
spec_format: use-case-2.0
area: analyse
---

# Spec: Analysepfade — Einstieg (Buy) und Wiederbewertung (Sell)  (`analyse-pipelines`)

> Konzept-Herkunft: (← C-011)

> **Schicht 3 von 3.** Testbares **Verhalten + Verträge**, sprach-/paradigma-unabhängig (Intent, keine Idiome/Klassen).
> **Source of Truth** für `coder` (baut daraus), `tester` (testet die Acceptance-Kriterien + Coverage-Gate), `reviewer` (prüft den Diff dagegen — hartes Drift-Gate).

## Zweck

Definiert zwei bewusst getrennte Analysepfade: (a) **Analyse neue Titel** bewertet Kandidaten für den Einstieg und erzeugt bei genügender Stärke ein Buy-Signal; (b) **Analyse bestehende Titel** bewertet gehaltene Positionen ausschliesslich gegen die beim Kauf fixierten Exit-Regeln neu und erzeugt bei Erfüllung ein Sell-Signal mit Dringlichkeitsstufe. Idea-Generation und Position-Monitoring bleiben getrennt.

## Main Success Scenario   <!-- (a) Analyse neue Titel -->

1. Der Pfad „neue Titel" erhält einen Kandidaten inkl. Signal-Bündel (Kennzahlen, Liquidität, Volatilität) von der Datenquellen-Abfrage.
2. Er berechnet den Gesamtscore mit dem gemeinsamen Framework (`[[analyse-framework]]`) — 5 Kategorien, Methodenscores 1–10, Ranking-gewichtet, Kategoriegewichte je Anlageklasse.
3. Er wendet die Score-Schwellen an; bei Gesamtscore ≥ 8 (KAUF) entsteht ein Buy-Signal.
4. Er übergibt das Buy-Signal (Titel + Score) an das Position-Sizing (`[[sizing]]`).

## Alternative Flows

### A1: (b) Analyse bestehende Titel — Wiederbewertung
- Ein Überwachungs-Ereignis (aus `[[depot-ueberwachung]]`) plus die beim Kauf fixierten Exit-Regeln kommen herein.
- Der Pfad prüft den aktuellen Zustand **nur** gegen diese fixierten Exit-Regeln (kein Neuverhandeln der Kaufschwelle), geleitet von der Frage „Würden wir die Position heute kaufen, wenn wir sie nicht hielten?".
- Ist eine Exit-Bedingung erfüllt, entsteht ein Sell-Signal mit Dringlichkeit **Hard-Exit** oder **Soft-Exit** → an das Exit-Sizing (`[[sizing]]`).

### A2: Buy-Pfad ohne Kauf-Signal
- Liegt der Gesamtscore unter 8, entsteht kein Buy-Signal (BEOBACHTEN/HALTEN/REDUZIEREN/VERKAUF führen nicht zu Position-Sizing).

### E1: Datengrundlage einer Kategorie fehlt
- Fehlt die Datengrundlage einer ganzen Analysekategorie, wird der Titel übersprungen (No-Evidence-No-Trade) und **nicht** durch eine LLM-Schätzung ersetzt (→ LLM-Grounding, `[[llm-grounding]]`).

## Acceptance-Kriterien

- **AC1** — Der Pfad „neue Titel" berechnet den Gesamtscore über das gemeinsame Framework (`[[analyse-framework]]`) und erzeugt ein Buy-Signal genau dann, wenn der Gesamtscore ≥ 8 ist (KAUF-Schwelle). Bei Score < 8 entsteht kein Buy-Signal (deckt A2).
- **AC2** — Ein erzeugtes Buy-Signal enthält mindestens Titel + Gesamtscore und wird an das Position-Sizing (`[[sizing]]`) übergeben; die beiden Analysepfade sind getrennt (ein Buy-Pfad erzeugt nie ein Sell-Signal und umgekehrt).
- **AC3** — Für jede im Output referenzierte Zahl gelten die LLM-Grounding-Verträge (`[[llm-grounding]]`): strukturierter Output mit Quellen-ID + Zeitstempel, deterministischer Zahlen-Cross-Check, und das LLM steht nie im Order-Pfad (Buy-Signal-Erzeugung ist deterministisch).
- **AC4** — Fehlt die Datengrundlage einer ganzen Analysekategorie, wird der Titel übersprungen und nicht durch eine geschätzte Zahl ersetzt (No-Evidence-No-Trade, deckt E1).
- **AC5** — Der Pfad „bestehende Titel" bewertet ausschliesslich gegen die beim Kauf fixierten Exit-Regeln des Titels; er verhandelt weder Kaufschwelle noch These neu („kein moving the goalposts"). Die Leitfrage „Würden wir die Position heute kaufen?" ist als Entscheidungsregel abgebildet.
- **AC6** — Ist eine Exit-Bedingung erfüllt, erzeugt der Pfad „bestehende Titel" ein Sell-Signal mit einer Dringlichkeitsstufe und übergibt es an das Exit-Sizing (`[[sizing]]`).
- **AC7** — Die Dringlichkeit ist **Hard-Exit**, wenn die These fundamental gebrochen ist (mindestens: Hack, Betrug, Delisting, Insolvenz) → „sofort"; andernfalls **Soft-Exit** bei Verschlechterung ohne Katastrophe → „gestaffelt möglich".
- **AC8** — Der Drawdown-Trigger (Default, provisorisch, konfigurierbar) löst eine Wiederbewertung (Review) aus, wenn der Kurs 20 % vom Hoch **oder** 10 % vom Einstand gefallen ist **und** der Titel gleichzeitig underperformt — nicht als blinder Stop, sondern als Review. Die Schwellen sind konfigurierbar.
- **AC9** — Der je Position anzuwendende Stop-Typ folgt der beim Kauf hinterlegten Strategie (Default, provisorisch, konfigurierbar): Value → fundamentaler Stop (kein reiner Kurs-Stop); Momentum → ATR-Trailing mit Multiplikator 2.5–3×; Buy-and-Hold → weiter Stop 25–30 % oder keiner.
- **AC10** — Der Time-Box-Trigger (Default, provisorisch, konfigurierbar) erzwingt nach einer definierten Frist ohne Bewegung eine Entscheidung/Review. Frist und Einordnung in Hard/Soft sind konfigurierbar (offener Punkt, siehe Edge-Cases).

> **Traceability:** Jeder Test trägt das kanonische Trace-Tag `@trace analyse-pipelines#AC<n>`.

## Verträge

- **(a) Input neue Titel:** Kandidat + Signal-Bündel `{ titel_id, anlageklasse, kennzahlen[], liquiditaet, volatilitaet, quellen_ids[] }` von der Datenquellen-Abfrage.
- **(a) Output neue Titel (Buy-Signal → `[[sizing]]`):** `{ titel_id, gesamtscore, kategorie_scores[5], fakten_mit_quellen[], zeitstempel }`.
- **(b) Input bestehende Titel:** Überwachungs-Ereignis (aus `[[depot-ueberwachung]]`) + `{ titel_id, exit_regeln (Stop-Loss, Take-Profit, Thesis-Invalidierung, optional Time-Box), strategie, einstand, hoch_seit_kauf }` aus dem Depot.
- **(b) Output bestehende Titel (Sell-Signal → `[[sizing]]`):** `{ titel_id, dringlichkeit: hard|soft, ausloeser, rohwerte, zeitstempel }`.
- **Score-Schwellen (aus Framework, 0–10):** ≥ 8 KAUF · 6–7.9 BEOBACHTEN · 4–5.9 HALTEN · 2–3.9 REDUZIEREN · < 2 VERKAUF.

## Edge-Cases & Fehlerverhalten

- **Thesis-Bruch-Operationalisierung (offen):** Welche konkrete News/Kennzahl die These als „fundamental gebrochen" markiert, ist konfigurierbar zu hinterlegen; bis dahin gilt die Enum aus AC7 (Hack/Betrug/Delisting/Insolvenz) als provisorischer Default.
- **Time-Box-Einordnung (offen):** Ob ein ausgelöster Time-Box-Trigger Hard oder Soft ist, ist konfigurierbar; Default-Einordnung ist Soft-Exit (Review).
- Sanity-Cap des Frameworks (Gesamtsignal max. „Halten" bei Risiko-Score < 3) bleibt gültig und kann ein Buy-Signal verhindern, auch wenn andere Kategorien hoch sind.
- Der ATR-Multiplikator je Volatilitätsklasse ist im Rahmen von AC9 konfigurierbar (offener Punkt aus C-011).

## NFRs

- Beide Pfade sind deterministische Module; das LLM ist ausschliesslich Analyse-Assistent und nie im Signal-/Order-Pfad (harte Architektur-Regel, → C-008).

## Nicht-Ziele

- Keine Bestimmung der Ordergrösse oder Tranchierung (das leistet `[[sizing]]`).
- Keine Portfolio-/Korrelationsprüfung (das leistet das Risikomanagement, nur auf der Kaufseite).
- Keine Definition des Score-Frameworks selbst (liegt in `[[analyse-framework]]`).

## Abhängigkeiten

- `[[analyse-framework]]` (Score-System, Gewichte, Schwellen, Sanity-Cap)
- `[[llm-grounding]]` (Grounding-Verträge, No-Evidence-No-Trade)
- `[[depot-ueberwachung]]` (liefert Überwachungs-Ereignisse für den Sell-Pfad)
- `[[sizing]]` (Position-Sizing empfängt Buy-Signale, Exit-Sizing empfängt Sell-Signale)
- Depotmodul (liefert beim Kauf fixierte Exit-Regeln, Strategie, Einstand, Hoch)
