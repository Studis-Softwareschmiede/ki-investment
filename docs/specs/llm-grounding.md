---
id: llm-grounding
title: LLM-Grounding (5 Sicherungen, Halluzinations-KPI)
status: active
version: 1
spec_format: use-case-2.0
area: analyse
---

# Spec: LLM-Grounding (5 Sicherungen, Halluzinations-KPI)  (`llm-grounding`)

> Konzept-Herkunft: (← C-008)

> **Schicht 3 von 3.** Testbares **Verhalten + Verträge**, sprach-/paradigma-unabhängig (Intent, keine Idiome/Klassen).
> **Source of Truth** für `coder` (baut daraus), `tester` (testet die Acceptance-Kriterien + Coverage-Gate), `reviewer` (prüft den Diff dagegen — hartes Drift-Gate).

## Zweck
Querschnitts-Sicherung, die verhindert, dass LLM-Halluzinationen (erfundene Fakten, falsche Zahlen, fabrizierte Quellen) in Kauf-/Verkaufsentscheidungen einfließen. Grundprinzip: **Das LLM darf denken, aber nicht behaupten und nicht handeln.** Jede Zahl kommt aus einer Datenquelle; jede Entscheidung trifft ein deterministisches Modul. Diese Spec formuliert die fünf Sicherungen als testbare Verträge plus das Halluzinations-Monitoring.

## Main Success Scenario
1. Das LLM erhält alle für die Analyse benötigten Zahlen als strukturierten Input (Quellen-ID + Timestamp je Zahl).
2. Das LLM liefert einen Analyse-Output als JSON nach festem Schema (Score je Kategorie 0–10, verwendete Fakten mit Quellen-IDs, Begründung).
3. Der Output wird gegen das JSON-Schema validiert (erster Halluzinationsfilter).
4. Ein deterministisches Prüfmodul (kein LLM) vergleicht jede referenzierte Zahl gegen ihre Originalquelle; liegt die Abweichung innerhalb der Toleranz, gilt die Analyse als geerdet.
5. Der validierte Score fließt als Eingabe in die deterministische Entscheidungskette (Signal, Sizing, Risiko, Order) — das LLM selbst berührt den Order-Pfad nicht.
6. Die Halluzinations-Quote wird laufend aus dem Cross-Check fortgeschrieben.

## Alternative Flows
### E1: Schema-Verletzung
- Verletzt der Output das JSON-Schema, wird er abgelehnt und der Vorfall protokolliert.

### E2: Cross-Check-Abweichung über Toleranz
- Überschreitet eine referenzierte Zahl die konfigurierte Toleranz gegenüber der Originalquelle, wird die Analyse verworfen und der Vorfall protokolliert.

### E3: Fehlende Evidenz
- Fehlt für eine Analysekategorie die Datengrundlage, wird kein LLM-geschätzter Score eingesetzt; der Titel wird übersprungen (No-Evidence-No-Trade).

### E4: Halluzinations-KPI über Schwellwert
- Übersteigt die Halluzinations-Quote den Schwellwert, wird ein Alarm ausgelöst und das LLM aus der Entscheidungskette genommen.

## Acceptance-Kriterien

- **AC1** — Grounding-Pflicht: Jede im Analyse-Output referenzierte Kennzahl/Zahl trägt eine **Quellen-ID und einen Timestamp**; ein Output mit einer Zahl ohne Quellen-ID oder ohne Timestamp wird abgelehnt.
- **AC2** — Input-Bindung: Das LLM verwendet ausschließlich Zahlen aus dem strukturierten Input; jede Zahl im Output muss auf eine Zahl des Inputs rückführbar sein. Ein Output, der eine input-fremde Zahl enthält, wird abgelehnt.
- **AC3** — Strukturierter Output: Der Analyse-Output wird gegen ein festes JSON-Schema validiert (Score je Kategorie 0–10, Fakten mit Quellen-IDs, Begründung). Ein Output, der das Schema verletzt, wird abgelehnt (deckt E1).
- **AC4** — Deterministischer Zahlen-Cross-Check: Jede referenzierte Zahl wird ohne LLM-Beteiligung gegen die Originalquelle geprüft. Überschreitet die Abweichung die konfigurierte Toleranz, wird die Analyse **verworfen und der Vorfall protokolliert** (deckt E2).
- **AC5** — Die Toleranzschwellen des Cross-Checks sind **konfigurierbare Parameter je Kennzahl-Typ** (absolute vs. relative Abweichung); ihre konkrete Festlegung ist **offen/provisorisch** und darf ohne Codeänderung angepasst werden.
- **AC6** — No-Evidence-No-Trade: Fehlt für eine Analysekategorie die Datengrundlage, wird der Score **nicht** durch eine LLM-Schätzung ersetzt; der Titel wird übersprungen (deckt E3; geteilte Regel mit [[analyse-framework]]).
- **AC7** — LLM nie im Order-Pfad: Buy-Signal, Position-Sizing, Exit-Sizing, Risiko-Gate und Order-Ausführung werden ausschließlich von deterministischen Modulen erzeugt; kein Modul des Order-Pfads ruft das LLM auf oder lässt sich vom LLM übersteuern (harte Architektur-Regel — das LLM liefert nur Score + Begründung).
- **AC8** — Halluzinations-KPI: Aus dem Cross-Check (AC4) wird laufend die Quote „Analysen mit Faktenabweichung" (verworfene Analysen / geprüfte Analysen) berechnet und bereitgestellt.
- **AC9** — Übersteigt die Halluzinations-Quote **2 %**, wird ein Alarm ausgelöst und das LLM aus der Entscheidungskette genommen (keine LLM-basierten Analysen fließen mehr in Entscheidungen ein), bis die Ursache geklärt ist. Der Schwellwert 2 % ist konfigurierbar (deckt E4).
- **AC10** — Auditierbarkeit: Jede abgelehnte oder verworfene Analyse (Grounding-Verstoß, Schema-Verletzung, Cross-Check-Abweichung) wird mit Grund, Zeitpunkt und betroffener Kennzahl/Quelle protokolliert.

> **Traceability:** Jeder Test trägt das kanonische Trace-Tag `@trace llm-grounding#AC<n>[,BR-NNN]`
> gemäss `knowledge/<lang>.md` → `## Spec-Tagging`. Der `tester` rechnet das Coverage-Gate
> (jede genannte AC + jede referenzierte BR ≥ 1 deckender Test).

## Verträge

**Analyse-Input (an das LLM):** `{ titel, anlageklasse, fakten: [ { kennzahl_typ, wert, quellen_id, timestamp } ] }` — alle Zahlen strukturiert und geerdet.

**Analyse-Output (JSON-Schema, Validierung als AC3):**
`{ scores: { fundamental, technisch, qualitativ, makro, risiko: 0–10 | fehlt }, fakten: [ { kennzahl_typ, wert, quellen_id, timestamp } ], begruendung: text }`

**Cross-Check-Modul (deterministisch):**
Input `{ output_fakten, originalquellen, toleranz_config: je Kennzahl-Typ }` → Output `{ status: geerdet | verworfen, abweichungen: [ { kennzahl_typ, wert_output, wert_quelle, abweichung, toleranz } ], protokoll_eintrag }`.

**Halluzinations-KPI:** `quote = verworfene_analysen / geprüfte_analysen` über ein Zeitfenster; `alarm = quote > schwellwert (Default 2 %)`. Ohne explizit übergebenes Zeitfenster misst die Quote kumulativ seit dem letzten Reset (Systemstart oder manuelle Reaktivierung). Ein einmal ausgelöster Alarm/Kill bleibt bestehen (Latch), bis manuell reaktiviert — unabhängig davon, ob nachfolgend registrierte Analysen die Quote rechnerisch wieder unter den Schwellwert drücken würden; die manuelle Reaktivierung startet zugleich ein frisches Beobachtungsfenster.

**Order-Pfad-Invariante (AC7):** Die Menge der Module {Buy-Signal, Position-Sizing, Exit-Sizing, Risiko-Gate, Order-Ausführung} enthält keinen LLM-Aufruf.

## Edge-Cases & Fehlerverhalten
- Zahl im Output ohne Quellen-ID/Timestamp → Ablehnung (AC1).
- Zahl im Output, die nicht im Input vorkam → Ablehnung (AC2).
- Originalquelle für Cross-Check nicht verfügbar → Analyse nicht als geerdet freigegeben (konservativ verwerfen + protokollieren).
- Toleranzschwelle für einen Kennzahl-Typ nicht konfiguriert → definierter Default greift; fehlender Default → verwerfen statt durchlassen.
- Halluzinations-Quote genau am Schwellwert (= 2 %) → kein Alarm; Alarm erst bei Überschreitung (> 2 %).

## NFRs
- Der Cross-Check ist deterministisch und reproduzierbar (gleiche Eingaben → gleiches Ergebnis), ohne LLM-Beteiligung.
- Protokolleinträge sind auditierbar und dürfen keine Secrets/API-Keys im Klartext enthalten.

## Nicht-Ziele
- Kein konkretes Feld-für-Feld-JSON-Schema (Detaillierung gehört in die Umsetzungsphase; hier nur die verpflichtenden Bestandteile).
- Keine Score-Berechnungslogik selbst (→ [[analyse-framework]]).
- Kein Mapping, welches Finanz-Plugin welche Kategorie erdet (eigene Integrations-Spec).

## Abhängigkeiten
- [[analyse-framework]] — Konsument der geerdeten Scores; teilt die No-Evidence-No-Trade-Regel.
- [[anlageklassen-config]] — Kategorien/Klassen, für die geerdete Scores erzeugt werden.
- Datenquellen-Abfrage / Finanz-Plugins — liefern den geerdeten strukturierten Input (eigene Specs, folgen).
