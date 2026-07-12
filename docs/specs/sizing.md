---
id: sizing
title: Sizing — Position-Sizing (Kauf) & Exit-Sizing (Verkauf)
status: active
version: 1
spec_format: use-case-2.0
area: handel
---

# Spec: Sizing — Position-Sizing (Kauf) & Exit-Sizing (Verkauf)  (`sizing`)

> Konzept-Herkunft: (← C-013)

> **Schicht 3 von 3.** Testbares **Verhalten + Verträge**, sprach-/paradigma-unabhängig (Intent, keine Idiome/Klassen).
> **Source of Truth** für `coder` (baut daraus), `tester` (testet die Acceptance-Kriterien + Coverage-Gate), `reviewer` (prüft den Diff dagegen — hartes Drift-Gate).

## Zweck

Bestimmt die Grösse und die Ausführungsform von Aufträgen. **Position-Sizing** (Mikro, Kaufseite) legt fest, wie viel von einem Titel gekauft wird — auf Basis Signalstärke, Einzeltitel-Risiko und erwarteter Kosten. **Exit-Sizing** (Verkaufsseite) legt fest, wie verkauft wird — alles auf einmal oder gestaffelt, mit welchem Order-Typ. Exit-Sizing umgeht bewusst das Risikomanagement.

## Main Success Scenario   <!-- Position-Sizing (Kauf) -->

1. Position-Sizing erhält ein Buy-Signal (Titel + Score) aus der Analyse neue Titel und die erwarteten Kosten (Courtage + Spread + geschätzte Slippage) von den Handelsplattformen.
2. Es berechnet die risikoadjustierte Grösse per Fractional-Kelly (bei genügend Trades) bzw. Fixed-Fractional (vorher).
3. Es begrenzt die Grösse durch das harte Risiko-Cap je Trade.
4. Es zieht die erwarteten Kosten ab und verkleinert oder verwirft den Trade, wenn die Kosten den erwarteten Gewinn auffressen.
5. Es übergibt die geplante Ordergrösse an die nachgelagerte Strategie-/Zeithorizont-Stufe (→ Risikomanagement).

## Alternative Flows

### A1: Exit-Sizing (Verkauf)
- Exit-Sizing erhält ein Sell-Signal + Dringlichkeit (Hard/Soft) aus der Analyse bestehende Titel, dazu Liquidität/Volatilität (Datenquellen-Abfrage) und erwartete Kosten.
- Es bestimmt Menge, Tranchierung, Order-Typ und Preis primär nach der Dringlichkeit und übergibt den Verkaufsauftrag direkt an das Kauf- & Verkaufsmodul (umgeht das Risikomanagement bewusst).

### A2: Zu wenig Trade-Historie für Kelly
- Sind weniger als das Minimum (Default 50–100 Simulations-Trades) gesammelt, wird nicht Kelly, sondern die konservative Fixed-Fractional-Regel verwendet.

### E1: Negatives oder null Kelly / unwirtschaftlicher Trade
- Ist das berechnete Kelly ≤ 0 oder verbleibt nach Kostenabzug kein positiver erwarteter Gewinn, wird kein Trade erzeugt.

### E2: Order unter Mindestgrösse
- Unterschreitet die geplante Ordergrösse die konfigurierte Mindest-Ordergrösse (Mindestgebühr-Effekt), wird der Trade nicht ausgeführt.

## Acceptance-Kriterien

- **AC1** — Position-Sizing berechnet die Kelly-Fraktion nach `f* = (b·p − q)/b` (p = Win-Wahrscheinlichkeit, q = 1−p, b = Gewinn/Verlust-Verhältnis). Ist `f*` ≤ 0, wird kein Trade erzeugt (deckt E1, „negatives Kelly → kein Trade").
- **AC2** — Standard-Fraktion ist Half-Kelly (Default, provisorisch, konfigurierbar); für volatile Anlageklassen (z. B. Krypto) gilt Quarter-Kelly, und Quarter-Kelly wirkt zugleich als Obergrenze der eingesetzten Fraktion. Die Fraktionen sind konfigurierbar.
- **AC3** — Zusätzlich zur Kelly-Fraktion greift ein hartes Cap: das Risiko je Trade ist auf 1–2 % des Kapitals begrenzt (Default, provisorisch, konfigurierbar). Das Cap gilt unabhängig davon, was Kelly vorschlägt (die kleinere der beiden Grössen gewinnt).
- **AC4** — Kelly wird erst „scharf" angewendet, wenn ≥ 50–100 abgeschlossene Trades im Simulationsmodus vorliegen (Default, provisorisch, konfigurierbar); darunter wird die konservative Fixed-Fractional-Regel verwendet (deckt A2).
- **AC5** — Vor dem Trade werden die erwarteten Kosten (Courtage + Spread + geschätzte Slippage) einkalkuliert; sie reduzieren die Grösse oder verwerfen den Trade, wenn nach Kostenabzug kein positiver erwarteter Gewinn verbleibt (Pre-Trade-Kostenkalkulation).
- **AC6** — Unterschreitet die geplante Ordergrösse die konfigurierte Mindest-Ordergrösse, wird kein Auftrag erzeugt (deckt E2). Die Mindest-Ordergrösse ist ein konfigurierbarer Parameter.
- **AC7** — Position-Sizing betrachtet nur den einzelnen Titel (Mikro); es nimmt keine Portfolio-/Korrelationsprüfung vor (die macht das nachgelagerte Risikomanagement).
- **AC8** — Exit-Sizing bestimmt die Ausführung primär nach der Dringlichkeit: Hard-Exit → sofort die gesamte Position, Order-Typ Market bzw. Stop-Market; Soft-Exit → gestaffelt, Order-Typ Limit als Default.
- **AC9** — Limit-Default-Regel: über alle Ausführungen sollen ≥ 95 % Limit-Orders sein; Market-Orders nur im Notfall (Hard-Exit) — als messbare Betriebs-Kennzahl geführt (Default, provisorisch, konfigurierbar).
- **AC10** — Für grosse Positionen relativ zum Handelsvolumen wird TWAP (time-weighted average price) verwendet, um den Marktimpact zu minimieren; die Auslöse-Schwelle (Positionsgrösse relativ zum Volumen) ist konfigurierbar.
- **AC11** — Gestaffelte Verkäufe werden in 3–4 Tranchen zerlegt (Default, provisorisch, konfigurierbar), deren Abstand zeit- oder ereignisbasiert (weitere −X % oder weitere negative News) ausgelöst wird.
- **AC12** — Exit-Sizing übergibt den Verkaufsauftrag direkt an das Kauf- & Verkaufsmodul und läuft dabei bewusst **nicht** durch das Risikomanagement (Verkauf reduziert Risiko).

> **Traceability:** Jeder Test trägt das kanonische Trace-Tag `@trace sizing#AC<n>`.

## Verträge

- **Position-Sizing Input:** Buy-Signal `{ titel_id, score, anlageklasse }` (aus `[[analyse-pipelines]]`) + erwartete Kosten `{ courtage, spread, slippage_est }` (Handelsplattformen).
- **Position-Sizing Output:** `{ titel_id, ordergroesse, eingesetzte_kelly_fraktion, risiko_pct, verworfen?: grund }` → Anlagestrategie + Zeithorizont → Risikomanagement.
- **Exit-Sizing Input:** Sell-Signal `{ titel_id, dringlichkeit: hard|soft }` (aus `[[analyse-pipelines]]`) + `{ liquiditaet, volatilitaet }` (Datenquellen-Abfrage) + erwartete Kosten + hinterlegte Strategie/Zeithorizont.
- **Exit-Sizing Output:** Verkaufsauftrag `{ titel_id, menge, tranchen[], order_typ: market|stop_market|limit|twap, preis?, ausfuehrungsprofil }` → Kauf- & Verkaufsmodul.
- **Konfiguration:** Kelly-Fraktion je Anlageklasse, Trade-Cap %, Trade-Minimum für Kelly-Schärfung, Mindest-Ordergrösse, Limit-Anteil-Ziel (Default 95 %), TWAP-Schwelle, Default-Tranchenzahl.

## Edge-Cases & Fehlerverhalten

- **Score→Win-Wahrscheinlichkeit-Mapping (offen):** Die Ableitung von `p` aus dem Analyse-Score ist konfigurierbar zu hinterlegen; bis dahin nutzt Kelly ein provisorisches Mapping und bleibt konservativ (Fixed-Fractional als Rückfall).
- **Stop-Market vs. Stop-Limit:** Für kritische Not-Ausstiege (Hard-Exit) wird Stop-Market gewählt (Fill sicher, Preis nicht), nicht Stop-Limit (Gap-Risiko lässt ungeschützt).
- Kosten je Tranche (mehrfache Courtage) fliessen in die Tranchen-Entscheidung ein; zu kleine Tranchen werden zusammengefasst.
- Portfolio-weiter Kelly-Cap (Gesamt-Exposure) ist bewusst **nicht** Teil dieses Moduls, sondern des Risikomanagements (→ C-015).

## NFRs

- Sizing-Berechnungen sind deterministisch und reproduzierbar (dieselben Inputs → dieselbe Grösse); das LLM ist nie beteiligt (→ C-008).

## Nicht-Ziele

- Kein Portfolio-weites Risiko-/Korrelations-Gate (Risikomanagement, nur Kaufseite).
- Keine Order-Ausführung selbst (Kauf- & Verkaufsmodul).
- Keine Definition der Exit-Regeln (die entstehen beim Kauf, → C-014; geprüft in `[[analyse-pipelines]]`).

## Abhängigkeiten

- `[[analyse-pipelines]]` (liefert Buy-Signale ans Position-Sizing, Sell-Signale + Dringlichkeit ans Exit-Sizing)
- `[[datenquellen-abfrage]]` (Liquidität/Volatilität für Exit-Sizing)
- Handelsplattformen (erwartete Kosten: Courtage, Spread, geschätzte Slippage)
- Kauf- & Verkaufsmodul (Empfänger der Verkaufsaufträge)
- Risikomanagement (nachgelagert auf der Kaufseite; von Verkäufen bewusst umgangen, → C-015)
