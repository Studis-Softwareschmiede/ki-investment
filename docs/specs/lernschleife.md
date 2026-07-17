---
id: lernschleife
title: Lernschleife (Research + zweistufiges Validierungs-Gate)
status: active
version: 1
spec_format: use-case-2.0
area: lernschleife
---

# Spec: Lernschleife (Research + zweistufiges Validierungs-Gate)  (`lernschleife`)

> Konzept-Herkunft: (← C-012)

> **Schicht 3 von 3.** Testbares **Verhalten + Verträge**, sprach-/paradigma-unabhängig (Intent, keine Idiome/Klassen).
> **Source of Truth** für `coder` (baut daraus), `tester` (testet die Acceptance-Kriterien + Coverage-Gate), `reviewer` (prüft den Diff dagegen — hartes Drift-Gate).

## Zweck

Die Lernschleife verbessert die Suchkriterien datengetrieben: **Research** analysiert Tagesgewinner/-verlierer und liefert **nur Hypothesen** (nie einen Direkt-Eingriff), ein **zweistufiges Validierungs-Gate** (historisch + Paper-Bewährung) prüft jede Hypothese gegen harte Zahlen und entscheidet per **Ampel-Logik**, ob eine Regel übernommen wird. Grundsatz: «Keine Regel geht ohne Zahlen durch.»

> **Stufe 2 — Umsetzung NACH dem MVP.** Diese Capability gehört bewusst nicht in den MVP (← C-005); ihr **Design ist beschlossen (v1.1)** und hier festgehalten. Die Paper-Bewährungs-Metriken (PSR/MinTRL) sind davon unabhängig bereits MVP-relevant, werden hier aber im Kontext des Gates spezifiziert.

## Main Success Scenario   <!-- Hypothese → Gate → Ampel -->

1. **Research** läuft periodisch, vergleicht die tatsächlichen Tagesgewinner/-verlierer mit dem, was die aktuellen Suchkriterien gefunden hätten, und sucht **erklärbare, marktlogische** Muster in den verpassten Fällen.
2. Research formuliert je Muster eine **Hypothese mit Mindest-Evidenz-Protokoll** (Anzahl Fälle, Zeitraum, Signalquelle/Anlageklasse) und übergibt sie an das Validierungs-Gate — **ohne** selbst Parameter zu tunen oder die Suchkriterien zu ändern.
3. Das Gate registriert die Hypothese in der **Trial-Registry** (jede getestete Variante wird gezählt) und startet **Stufe A (historisch)**.
4. Stufe A testet gegen Point-in-Time-saubere Historie: Mindest-Stichprobe, Walk-Forward mit Embargo, Walk-Forward-Effizienz und Deflated Sharpe Ratio.
5. Besteht Stufe A, geht die Regel in **Stufe B (Paper-Bewährung)** und läuft im Simuliert-Modus mit; PSR und laufende MinTRL werden berechnet und angezeigt.
6. Das Gate gibt eine **Ampel** aus (🟢/🟡/🔴). Nur bei 🟢 wird die Regel an die Suchkriteria übergeben.

## Alternative Flows

### A1: Stufe A bestanden, Stufe B läuft noch (🟡)
- Die Regel wird noch nicht in die Suchkriteria übernommen, sondern läuft nur im Paper-Modus mit, bis Stufe B abgeschlossen ist.

### A2: Durchgefallen (🔴)
- Die Regel wird mit Begründung archiviert (nicht gelöscht) — die Trial-Registry braucht sie für die DSR-Korrektur.

### A3: Zu kleine Stichprobe
- Liegt die Trade-Zahl einer Hypothese unter der Mindestbewertungsgrenze, wird sie gar nicht bewertet (kein Urteil, keine Übernahme).

### E1: Point-in-Time-Historie für nachrichtengetriebene Signale fehlt
- Kann Stufe A für ein nachrichtengetriebenes Signal keine Point-in-Time-saubere Historie beziehen, wird die Hypothese nicht auf unsauberen Daten getestet, sondern als „nicht historisch prüfbar" markiert und geparkt (offener Punkt, siehe Nicht-Ziele/Abhängigkeiten).

## Acceptance-Kriterien

- **AC1** — Research liefert ausschliesslich **Hypothesen** an das Validierungs-Gate und ändert die Suchkriterien niemals direkt; jede Hypothese trägt ein Mindest-Evidenz-Protokoll (mindestens Anzahl Fälle, Zeitraum, Signalquelle/Anlageklasse).
- **AC2** — Research bewertet Muster auf marktlogische Erklärbarkeit; rein statistische Zufallsmuster ohne marktlogische Begründung werden nicht als Hypothese weitergegeben.
- **AC3** — Jede an das Gate übergebene Regelvariante wird in einer **Trial-Registry** gezählt — auch verworfene; ohne diese Zählung ist die Deflated Sharpe Ratio ungültig. Abgelehnte Regeln werden **archiviert, nie gelöscht**.
- **AC4** — **Stufe A (historisch)** bewertet eine Hypothese nur bei einer Mindest-Stichprobe von **≥ 100 Trades**; unter **30 Trades** wird gar nicht bewertet (deckt A3). *(Präzisierung, S-060: „Mindest-Stichprobe" (100) und „Bewertungs-Untergrenze" (30) sind zwei unabhängig konfigurierbare Schwellen (AC12) — dazwischen, bei 30–99 Trades, wird die Hypothese gezählt (AC3) und mit „durchgefallen" bewertet: sie erreicht die Mindest-Stichprobe für ein Bestehen nicht, ist aber nicht so klein, dass gar kein Urteil möglich wäre (das gilt nur unter 30).)*
- **AC5** — Stufe A führt einen **Walk-Forward mit 30-Tage-Embargo** zwischen Trainings- und Validierungsfenster durch (gegen Datenleckage); die Regel muss über alle sequentiellen Splits geprüft werden, nicht nur über einen.
- **AC6** — Stufe A verlangt eine **Walk-Forward-Effizienz ≥ 0.5** (Out-of-Sample-Rendite ≥ die Hälfte der In-Sample-Rendite); darunter gilt Overfit-Verdacht und die Hypothese besteht Stufe A nicht.
- **AC7** — Stufe A berechnet die **Deflated Sharpe Ratio (DSR)**, korrigiert um die aus der Trial-Registry bekannte Anzahl aller getesteten Regelvarianten.
- **AC8** — **Stufe B (Paper-Bewährung)** läuft nur für Regeln, die Stufe A bestanden haben, im Simuliert-Modus; sie besteht bei **Probabilistic Sharpe Ratio (PSR) ≥ 95 %** gegen Benchmark-Sharpe 0.
- **AC9** — In Stufe B wird bei jeder Auswertung die **MinTRL** (Minimum Track Record Length) laufend berechnet und angezeigt: die verbleibende Zeit, bis das Ergebnis beim aktuellen Sharpe mit 95 % Konfidenz von Null unterscheidbar ist (Richtwerte: Sharpe 1.0 ≈ 3 Jahre, Sharpe 0.5 ≈ 11 Jahre Monatsdaten).
- **AC10** — Das Gate gibt genau eine **Ampel** je Hypothese aus: 🟢 (beide Stufen bestanden) → Regel wird an die Suchkriteria übergeben; 🟡 (Stufe A bestanden, Stufe B läuft) → Regel läuft nur im Paper-Modus mit, nicht in den Suchkriterien (deckt A1); 🔴 (durchgefallen) → Regel wird mit Begründung archiviert (deckt A2).
- **AC11** — Nur eine 🟢-Regel wird in die Suchkriteria übernommen; weder Research noch das Gate umgehen diesen Pfad (validierte Regeln erreichen die Suchkriteria ausschliesslich über die Ampel).
- **AC12** — Alle Schwellen (Mindest-Stichprobe, Bewertungs-Untergrenze, Embargo-Dauer, WF-Effizienz, PSR-Schwelle) sind als Parameter konfigurierbar; die genannten Werte sind die beschlossenen Defaults.

> **Traceability:** Jeder Test trägt das kanonische Trace-Tag `@trace lernschleife#AC<n>`.

## Verträge

- **Research-Input:** Tagesgewinner/-verlierer über die geteilte Datenquellen-Abfrage (`[[datenquellen-abfrage]]`) + optional die aktuell aktiven Suchkriterien.
- **Hypothese (Research → Gate):** `{ hypothese_id, beschreibung, marktlogik, evidenz{ anzahl_faelle, zeitraum, signalquelle, anlageklasse } }`.
- **Trial-Registry-Eintrag:** `{ hypothese_id, variante, getestet_am, ergebnis (bestanden|abgelehnt|läuft), begründung }` — append-only, nie gelöscht.
- **Stufe-A-Report:** `{ n_trades, walk_forward_effizienz, embargo_tage, dsr }`.
- **Stufe-B-Report:** `{ psr, benchmark_sharpe (=0), mintrl_restlaufzeit }`.
- **Gate-Output (an `[[suchkriteria]]`):** `{ hypothese_id, ampel (grün|gelb|rot), metriken, begründung }`; nur `grün` erzeugt eine übernommene Regel.

## Edge-Cases & Fehlerverhalten

- Instabile Optima (Parameter springen stark zwischen Walk-Forward-Fenstern) gelten als nicht bestanden — „die stabilste" Einstellung schlägt „die profitabelste".
- Verdächtige Werte (Sharpe > 3.0, Win-Rate > 80 %) sind Overfit-Warnsignale und führen zu erhöhter Skepsis/Ablehnung, nicht zu automatischer Übernahme.
- Eine 🔴-Regel darf nie durch erneutes Einreichen unbemerkt die Trial-Zählung umgehen (jede erneute Prüfung zählt in der Registry).

## NFRs

- **Auditierbarkeit:** Die Trial-Registry ist vollständig und append-only; ohne vollständige Zählung ist die DSR statistisch ungültig.
- **Nachvollziehbarkeit:** Jede Ampel-Entscheidung trägt ihre Metriken und (bei 🔴) eine Begründung.

## Nicht-Ziele

- **Umsetzung im MVP** — diese Capability ist Stufe 2 (nach MVP); nur das Design ist hier fixiert (← C-005).
- **Direkter Eingriff von Research in die Suchkriterien** ist ausgeschlossen (Research liefert nur Hypothesen).
- **Klassisches historisches Backtesting als eigenes System** ist ersetzt durch dieses Gate + den Modus-Schalter echt/simuliert (← C-004).
- **Offen (bewusst nicht entschieden):** Bereitstellung einer Point-in-Time-Historie für nachrichtengetriebene Signale; Automatik vs. menschlicher Freigabe-Vorschlag bei Grenzfällen (Vorschlag: Gate prüft automatisch, legt bei Grenzfällen einen Freigabe-Vorschlag vor).

## Abhängigkeiten

- Datenquellen-Abfrage (`[[datenquellen-abfrage]]`) — Datenlieferant für Research und für die Point-in-Time-Historie.
- Suchkriteria (`[[suchkriteria]]`) — Empfänger 🟢-validierter Regeln.
- Kauf-/Verkaufsmodul im Simuliert-Modus (`[[kauf-verkauf]]`) — liefert das Trade-Log für die Paper-Bewährung (Stufe B).
- Point-in-Time-saubere Historie (Dateneingang, ← C-009/C-019) — Grundlage für Stufe A.
