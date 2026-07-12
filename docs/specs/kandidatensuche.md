---
id: kandidatensuche
title: Kandidatensuche — profilbasierte Suchkriteria je Anlageklasse
status: active
version: 1
spec_format: use-case-2.0
area: suche
---

# Spec: Kandidatensuche — profilbasierte Suchkriteria je Anlageklasse  (`kandidatensuche`)

> Konzept-Herkunft: (← C-010)

> **Schicht 3 von 3.** Testbares **Verhalten + Verträge**, sprach-/paradigma-unabhängig (Intent, keine Idiome/Klassen).
> **Source of Truth** für `coder` (baut daraus), `tester` (testet die Acceptance-Kriterien + Coverage-Gate), `reviewer` (prüft den Diff dagegen — hartes Drift-Gate).

## Zweck
Die Kandidatensuche (Suchkriteria) definiert, **wonach** gesucht wird, um neue Titel zu finden — profilbasiert je Anlageklasse statt als einheitlicher Filter. Sie liefert Filterkriterien an die geteilte Datenquellen-Abfrage; sie findet keine konkreten Titel selbst, sondern legt Schwellen und Signal-Kombinationen fest.

## Main Success Scenario
1. Die Suche wird für die aktiven Anlageklassen ausgelöst (eventbasiert bevorzugt, provisorischer Default).
2. Je aktiver Anlageklasse wird das zugehörige Suchprofil mit seinen konfigurierten Schwellen und Signal-Kombinationen geladen.
3. Die Querschnitt-Filter (Liquiditäts-Mindestschwelle, Volatilitäts-Fenster) werden auf jedes Profil angewandt.
4. Aus Profil + Querschnitt-Filtern werden Filterkriterien gebildet und an die Datenquellen-Abfrage (`[[dateneingang]]`) übergeben.
5. Kandidaten, die alle Pflicht-Bedingungen des Profils erfüllen, werden als Trefferliste an die Analyse neuer Titel weitergereicht.

## Alternative Flows
### A1: Inaktive Anlageklasse (Toggle aus)
- Für eine per Toggle deaktivierte Anlageklasse wird kein Suchprofil geladen und keine Abfrage ausgelöst (keine Verarbeitung, keine Datenkosten).

### A2: Periodischer Snapshot als Fallback
- Ist der eventbasierte Scanner für eine Anlageklasse nicht verfügbar/nicht sinnvoll, läuft die Suche als periodischer Snapshot-Scan im konfigurierten Intervall.

### A3: Regeländerung aus der Lernschleife
- Eine geänderte/neue Suchregel wird nur übernommen, wenn sie das Validierungs-Gate durchlaufen hat (Ampel 🟢); Vorschläge ohne Gate-Freigabe verändern die aktive Suche nicht.

### E1: Katalysator-Pflicht nicht erfüllt (Aktien Small/Mid)
- Ein Titel mit hohem RVOL, aber ohne News/Katalysator erfüllt das Small/Mid-Profil NICHT und wird nicht als Kandidat ausgegeben.

## Acceptance-Kriterien

- **AC1** — Die Suche nutzt je Anlageklasse ein eigenes Suchprofil; es gibt keinen einheitlichen Filter über alle Klassen. Ein Titel wird nur gegen das Profil seiner Anlageklasse geprüft.
- **AC2** — Profil Aktien Small-/Mid-Cap (Klasse 1): Relatives Volumen (RVOL) > 2× Durchschnitt ist non-negotiable (Pflichtbedingung); zusätzlich werden Kurs-Änderung am Tag / Gap-up, Low Float, RSI und Breakout über Widerstand berücksichtigt. Die RVOL-Schwelle ist ein konfigurierbarer Default (2×, provisorisch).
- **AC3** — Profil Aktien Small-/Mid-Cap: RVOL und Katalysator/News-Signal müssen als Kombination (UND) erfüllt sein — ein Titel ohne Katalysator/News wird trotz hohem RVOL nicht als Kandidat ausgegeben (deckt E1).
- **AC4** — Profil Aktien Large-Cap / ETFs (Klassen 1, 2): Selektion über Fundamentaldaten, Analysten-Revisionen (Earnings Revisions) und Fund Flows; Reddit/Social-Sentiment wird hier NICHT als Selektor verwendet.
- **AC5** — Profil Krypto (Klasse 7): Social-/Kommentar-Volumen, On-Chain-Signale (Whale-Bewegungen, Exchange-Flows, Smart-Money) und Funding-Rates; relatives Volumen > 2× Durchschnitt als Pflichtbedingung. Schwellen sind konfigurierbare Defaults (provisorisch).
- **AC6** — Querschnitt-Filter über alle Profile: eine Liquiditäts-Mindestschwelle (handelbares Volumen) und ein Volatilitäts-Fenster (nicht zu tot, nicht zu wild) werden auf jeden Kandidaten angewandt; ein Titel, der die Liquiditäts-Mindestschwelle unterschreitet oder ausserhalb des Volatilitäts-Fensters liegt, wird ausgeschlossen. Beide Schwellen sind konfigurierbar.
- **AC7** — Der Suchmodus ist konfigurierbar: eventbasierter Scanner als bevorzugter Default (provisorisch), periodischer Snapshot-Scan als Fallback (deckt A2). Die Wahl ist je Anlageklasse einstellbar.
- **AC8** — Änderungen an Suchregeln (neue/geänderte Kriterien oder Schwellen aus der Lernschleife) werden ausschliesslich über das Validierungs-Gate übernommen; nur Gate-freigegebene Regeln (Ampel 🟢) werden aktiv (deckt A3). Ein Regelvorschlag ohne Gate-Freigabe ändert die aktive Suche nicht.
- **AC9** — Für eine per Toggle deaktivierte Anlageklasse wird kein Suchprofil geladen und keine Datenquellen-Abfrage ausgelöst (keine Verarbeitung, keine Datenkosten) (deckt A1).
- **AC10** — Alle Schwellenwerte aller Profile (RVOL-Faktor, %-Kursänderung, Float-Grenze, RSI-Schwelle, Funding-Rate-, Liquiditäts- und Volatilitäts-Grenzen) sind konfigurierbar und ohne Codeänderung überschreibbar; sie sind als provisorische Defaults zu behandeln und im Simulationsmodus zu kalibrieren.
- **AC11** — Im MVP existieren mindestens die Profile für Aktien (Klasse 1), ETFs (Klasse 2) und Krypto (Klasse 7); Profile für weitere Klassen (Obligationen, FX, Rohstoffe, aktive Fonds, Infrastruktur, Derivate) sind optional ergänzbar, ohne die bestehenden Profile zu verändern.

> **Traceability:** Jeder Test trägt das kanonische Trace-Tag `@trace kandidatensuche#AC<n>[,BR-NNN]`
> gemäss `knowledge/<lang>.md` → `## Spec-Tagging`. Der `tester` rechnet das Coverage-Gate
> (jede genannte AC ≥ 1 deckender Test). Details: `docs/architecture/traceability-subsystem.md`.

## Verträge
- **Suchprofil (je Anlageklasse):** `{ anlageklasse: 1..11, pflicht_bedingungen[...], optionale_signale[...], schwellen: { ... konfigurierbar }, modus: eventbasiert|periodisch }`.
- **Querschnitt-Filter:** `{ liquiditaets_mindestschwelle, volatilitaets_fenster: { min, max } }` — auf alle Profile angewandt.
- **Output an Datenquellen-Abfrage:** Filterkriterien `{ anlageklasse, signale, schwellen }` (Vertrag mit `[[dateneingang]]`).
- **Output an Analyse neuer Titel:** Trefferliste `[{ titel, anlageklasse, erfuellte_kriterien[...] }]`.
- **Input aus Lernschleife:** validierte Regeländerung nur mit Gate-Status 🟢.

## Edge-Cases & Fehlerverhalten
- Hoher RVOL ohne Katalysator (Small/Mid) → kein Kandidat (AC3/E1).
- Reddit-Signal für Large-Cap/ETF vorhanden → wird ignoriert (kein Selektor, AC4).
- Free-Tier-Daten verzögert (15–20 min) → für zeitkritische Klassen (Krypto, Daytrade-Aktien) als unzureichend markieren; die Suche darf sich nicht auf verzögerte Daten als Echtzeit-Signal verlassen.
- Regelvorschlag ohne Gate-Freigabe → verworfen/geparkt, nie automatisch aktiv (AC8).
- Alle Schwellen auf provisorischen Defaults, noch nicht kalibriert → Betrieb nur im Simulationsmodus sinnvoll (AC10).

## NFRs
- Kosten-Disziplin: inaktive Klassen lösen keine Suche und keine Datenabfrage aus (AC9).
- Konfigurierbarkeit/Kalibrierbarkeit: sämtliche Schwellen als provisorische, im Simulationsmodus kalibrierbare Defaults (AC10).
- Regel-Governance: keine Regeländerung ohne Validierungs-Gate (AC8) — Schutz gegen Overfitting.

## Nicht-Ziele
- Depot-Suchkriterien (Überwachung bestehender Titel, Exit-Auslöser) sind eine eigene Capability, nicht Teil dieser Spec.
- Die eigentliche Score-/Kategorie-Bewertung der Kandidaten erfolgt in der Analyse neuer Titel, nicht hier.
- Die Bereitstellung/Aggregation der Signale (Liquidität, Volatilität, z-Scores) leistet die Datenquellen-Abfrage (`[[dateneingang]]`), nicht die Suche.

## Abhängigkeiten
- `[[dateneingang]]` (geteilte Datenquellen-Abfrage; liefert je Titel Signal-Bündel inkl. Liquidität + Volatilität und respektiert Anlageklassen-Toggles).
- Validierungs-Gate der Lernschleife (liefert validierte Regeländerungen; Stufe 2).
- Anlageklassen-Toggles aus der Konfiguration.
- Analyse neuer Titel als nachgelagerter Konsument der Trefferliste.
