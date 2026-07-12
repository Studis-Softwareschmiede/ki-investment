---
id: anlageklassen-config
title: Anlageklassen-Konfiguration (Feature-Toggles, Methoden & Gewichte)
status: active
version: 1
spec_format: use-case-2.0
area: konfiguration
---

# Spec: Anlageklassen-Konfiguration (Feature-Toggles, Methoden & Gewichte)  (`anlageklassen-config`)

> Konzept-Herkunft: (← C-005, C-006)

> **Schicht 3 von 3.** Testbares **Verhalten + Verträge**, sprach-/paradigma-unabhängig (Intent, keine Idiome/Klassen).
> **Source of Truth** für `coder` (baut daraus), `tester` (testet die Acceptance-Kriterien + Coverage-Gate), `reviewer` (prüft den Diff dagegen — hartes Drift-Gate).

## Zweck
Die 11 Anlageklassen sind **Feature-Toggles in den Systemeinstellungen**, keine Code-Grenzen. Diese Spec legt fest, wie Klassen aktiviert/deaktiviert werden, wie inaktive Klassen jede Verarbeitung und jeden Datenabruf unterbinden, wie mit offenen Positionen bei Deaktivierung umgegangen wird, und in welcher Form die klassenspezifischen Methodentabellen (mit festem Ranking je Methode) und Kategoriegewichte als versionierte Konfigurationsdaten vorliegen.

## Main Success Scenario
1. Der Nutzer öffnet die Anlageklassen-Einstellungen und sieht alle 11 Klassen als einzeln schaltbare An/Aus-Auswahl inkl. Empfehlungsstufe (Aktivierungsreihenfolge).
2. Der Nutzer aktiviert oder deaktiviert eine Klasse.
3. Das System speichert den Toggle-Zustand persistent auf Systemeinstellungs-Ebene.
4. Alle nachgelagerten Module (Kandidatensuche, Datenquellen-Abfrage, Analyse, Handelsplattformen, Depotstrategie) richten ihr Verhalten am aktuellen Toggle-Zustand aus: aktive Klassen werden verarbeitet, inaktive nicht.

## Alternative Flows
### A1: Deaktivierung einer Klasse mit offenen Positionen
- Der Nutzer deaktiviert eine Klasse, in der aktuell Positionen gehalten werden.
- Das System unterbindet ab sofort **neue Käufe** in dieser Klasse.
- Überwachung (Wiederbewertung bestehender Titel) und Exit-Ausführung (Verkäufe) der offenen Positionen laufen unverändert weiter.

### E1: Ungültige Gewichtungskonfiguration
- Eine Kategoriegewichtung, deren fünf Kategoriegewichte für eine Klasse nicht exakt 100 % ergeben, wird als ungültig zurückgewiesen und nicht wirksam.

## Acceptance-Kriterien

- **AC1** — Alle 11 Anlageklassen mit der verbindlichen Nummerierung erscheinen als einzeln An/Aus-schaltbare Toggles: 1 Aktien, 2 ETFs, 3 Cash/Geldmarkt, 4 Obligationen, 5 Aktive Fonds, 6 Immobilien, 7 Kryptowährungen, 8 Rohstoffe, 9 Infrastrukturfonds, 10 FX, 11 Derivate.
- **AC2** — Bei Erstinstallation sind genau die Klassen **Aktien, ETFs und Kryptowährungen** aktiv, alle übrigen acht inaktiv (MVP-Default gem. Beschluss Katalog a-1). Der Default-Zustand ist konfigurierbar.
- **AC3** — Jede Klasse trägt eine Empfehlungsstufe für die Aktivierungsreihenfolge (MVP / Stufe 2 / Stufe 3). Die Stufe ist reine Empfehlung und schränkt die Aktivierbarkeit **nicht** ein — jede Klasse ist jederzeit aktivierbar.
- **AC4** — Eine inaktive Klasse löst in **keinem** Modul Verarbeitung aus (Kandidatensuche, Datenquellen-Abfrage, Analyse, Handelsplattformen, Depotstrategie); insbesondere wird für eine inaktive Klasse **keine externe Datenquelle abgefragt** (keine Datenkosten).
- **AC5** — Wird der Toggle einer Klasse von aktiv auf inaktiv geschaltet, während offene Positionen in dieser Klasse bestehen, unterbleiben **neue Käufe** in dieser Klasse, während **Überwachung und Exit-Ausführung** (Verkäufe) der offenen Positionen aktiv bleiben (deckt A1). Ein Toggle darf niemals dazu führen, dass eine gehaltene Position unüberwacht bleibt.
- **AC6** — Für jede der 11 Klassen liegen die Kategoriegewichte der 5 Analysekategorien (Fundamental, Technisch, Qualitativ, Makro, Risiko & Quantitativ) als Konfigurationsdaten vor; die fünf Gewichte einer Klasse summieren sich auf **exakt 100 %**.
- **AC7** — Eine Kategoriegewichtung, deren fünf Gewichte für eine Klasse nicht exakt 100 % ergeben, wird als ungültig zurückgewiesen und nicht wirksam (deckt E1).
- **AC8** — Die hinterlegten Kategoriegewichte entsprechen exakt der Gewichtungstabelle im Abschnitt „Verträge" (u. a. Aktien 35/15/20/10/20, Cash 30/0/20/35/15, Krypto 18/22/15/20/25, Derivate 15/35/10/15/25).
- **AC9** — Für jede Klasse existiert je Analysekategorie eine Methodentabelle; jede Methode trägt ein **festes Ranking im Bereich 1–10**. Das Ranking ist klassenspezifisch und über einzelne Analysen hinweg konstant (kein Wert außerhalb 1–10 zulässig).
- **AC10** — Methodentabellen und Kategoriegewichte sind **versioniert**: jede Änderung erzeugt eine neue Version, und zu jeder durchgeführten Analyse ist nachvollziehbar, welche Konfigurationsversion ihr zugrunde lag.
- **AC11** — Das System weist **quartalsweise** auf die fällige Überprüfung der Rankings hin (Erinnerung/Kennzeichnung des Review-Bedarfs), ohne Ranking-Werte automatisch zu verändern (Prozess-Hinweis).
- **AC12** — Der Toggle-Zustand liegt auf Ebene der Systemeinstellungen (gleiche Ebene wie der Modus-Schalter echt/simuliert) und ist persistent über Neustarts hinweg.

> **Traceability:** Jeder Test trägt das kanonische Trace-Tag `@trace anlageklassen-config#AC<n>[,BR-NNN]`
> gemäss `knowledge/<lang>.md` → `## Spec-Tagging`. Der `tester` rechnet das Coverage-Gate
> (jede genannte AC + jede referenzierte BR ≥ 1 deckender Test).

## Verträge

**Toggle-Konfiguration (je Klasse):** `{ nummer: 1–11, name, aktiv: bool, empfehlungsstufe: MVP | Stufe 2 | Stufe 3 }`. Default aktiv: {1 Aktien, 2 ETFs, 7 Kryptowährungen}. Der persistierte `name` verwendet die Kurzform aus AC1 (z. B. `Cash/Geldmarkt`, `FX`, `Derivate`); die längeren Bezeichnungen der Verträge-Tabelle unten (`Cash / Geldmarkt`, `Fremdwährungen / FX`, `Derivate (Opt./Fut.)`) sind Anzeige-Label für Dokumentation/UI, keine zweite Datenquelle.

**Konsumenten-Kontrakt Toggle:** Kandidatensuche, Datenquellen-Abfrage, Analyse, Handelsplattformen und Depotstrategie erhalten je Klasse den Aktiv-Zustand und dürfen bei `aktiv = false` weder Verarbeitung noch Datenabruf für diese Klasse auslösen — mit der Ausnahme aus AC5 (Überwachung/Exit offener Positionen).

**Kategoriegewichte (versionierte Konfigurationsdaten, Summe je Zeile = 100 %):**

| # | Anlageklasse | Fundamental | Technisch | Qualitativ | Makro | Risiko & Quant | Empfehlung |
|---|---|---|---|---|---|---|---|
| 1 | Aktien | 35 % | 15 % | 20 % | 10 % | 20 % | MVP |
| 2 | ETFs | 30 % | 10 % | 30 % | 15 % | 15 % | MVP |
| 3 | Cash / Geldmarkt | 30 % | 0 % | 20 % | 35 % | 15 % | MVP |
| 4 | Obligationen | 30 % | 10 % | 10 % | 25 % | 25 % | Stufe 2 |
| 5 | Aktive Fonds | 30 % | 5 % | 30 % | 10 % | 25 % | Stufe 2 |
| 6 | Immobilien | 35 % | 5 % | 20 % | 20 % | 20 % | Stufe 2 |
| 7 | Kryptowährungen | 18 % | 22 % | 15 % | 20 % | 25 % | Stufe 3 |
| 8 | Rohstoffe | 30 % | 20 % | 5 % | 25 % | 20 % | Stufe 3 |
| 9 | Infrastrukturfonds | 35 % | 5 % | 20 % | 20 % | 20 % | Stufe 3 |
| 10 | Fremdwährungen / FX | 20 % | 25 % | 5 % | 30 % | 20 % | Stufe 3 |
| 11 | Derivate (Opt./Fut.) | 15 % | 35 % | 10 % | 15 % | 25 % | Stufe 3 |

> Hinweis: Die Empfehlungsstufe weicht bei Krypto bewusst vom MVP-Toggle-Default ab — Krypto ist als MVP-Klasse **aktiv** (Katalog a-1), in der klassischen Prio-Reihenfolge der Anlageklassen-Notiz jedoch als Stufe 3 geführt. Der Toggle-Default (AC2) hat Vorrang; die Empfehlung ist unverbindlich (AC3).

**Methodentabelle (je Klasse, je Kategorie):** Liste von Methoden `{ methoden_id, kurzbezeichnung, ranking: 1–10 }`. Die vollständigen Methodenlisten je Klasse (z. B. Aktien/Fundamental: DCF R9, ROE/ROIC R9, EV/EBITDA R8, KBV R6, KGV R7, Verschuldungsgrad R8, Earnings Revisions R7) werden 1:1 aus der Konzept-Quelle als Konfigurationsdaten übernommen und sind Eingabe für [[analyse-framework]].

**Version:** jede Konfigurationsdaten-Änderung liefert eine neue, referenzierbare Versions-Kennung; jede Analyse referenziert die genutzte Version.

## Edge-Cases & Fehlerverhalten
- Ranking-Wert außerhalb 1–10 → Konfiguration ungültig, wird nicht wirksam.
- Kategoriegewichte einer Klasse ≠ 100 % → ungültig (AC7).
- Deaktivierung einer Klasse ohne offene Positionen → sofort keinerlei Verarbeitung/Datenabruf für diese Klasse.
- Reaktivierung einer zuvor deaktivierten Klasse mit weiterhin offenen Positionen → neue Käufe wieder zulässig; keine rückwirkende Verarbeitung während der Inaktiv-Phase.

## NFRs
- Toggle-Änderungen wirken ohne Neustart auf nachgelagerte Module.
- Konfigurationsdaten (Gewichte, Methodentabellen, Versionen) sind nachvollziehbar auditierbar.

## Nicht-Ziele
- Keine Score-Berechnung selbst (→ [[analyse-framework]]).
- Kein automatisches Anpassen von Rankings/Gewichten (nur quartalsweiser Review-Hinweis, AC11).
- Keine Auswahl der Trading-API je Klasse (spätere Handelsplattform-Spec).

## Abhängigkeiten
- [[analyse-framework]] — Konsument der Kategoriegewichte und Methoden-Rankings.
- Kandidatensuche, Datenquellen-Abfrage, Handelsplattformen, Depotstrategie — respektieren den Klassen-Toggle (eigene Specs, folgen).
