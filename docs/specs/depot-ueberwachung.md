---
id: depot-ueberwachung
title: Depot-Überwachung (bestehende Titel)
status: active
version: 1
spec_format: use-case-2.0
area: suche
---

# Spec: Depot-Überwachung (bestehende Titel)  (`depot-ueberwachung`)

> Konzept-Herkunft: (← C-010)

> **Schicht 3 von 3.** Testbares **Verhalten + Verträge**, sprach-/paradigma-unabhängig (Intent, keine Idiome/Klassen).
> **Source of Truth** für `coder` (baut daraus), `tester` (testet die Acceptance-Kriterien + Coverage-Gate), `reviewer` (prüft den Diff dagegen — hartes Drift-Gate).

## Zweck

Überwacht laufend die im Depot gehaltenen Titel auf Ereignisse, die eine beim Kauf definierte Exit-Regel auslösen könnten (Gegenstück zur Kandidatensuche für neue Titel). Das Modul fällt **keinen** eigenen Verkaufs-Entscheid; es erkennt relevante Änderungen und gibt sie an die Analyse bestehender Titel weiter.

## Main Success Scenario   <!-- Position-Monitoring-Zyklus -->

1. Das Modul liest je gehaltenem Titel aus dem Depot: Titel-Identität + Anlageklasse (1–11), hinterlegte Strategie und die beim Kauf fixierten Exit-Regeln.
2. Es bestimmt anhand der Anlageklasse die relevanten Datenquellen und die je Klasse überwachten Grössen (profilbasiert, kein Einheitsfilter).
3. Es stellt gebündelt eine Abfrage je Titel an die geteilte Datenquellen-Abfrage (`[[datenquellen-abfrage]]`) und erhält ein Signal-Bündel (u. a. News, Kurs, Sentiment, Momentum, Liquidität, Volatilität; bei Krypto zusätzlich On-Chain-Grössen).
4. Es filtert die eingehenden News/Ereignisse gegen den Keyword-/Ereignis-Filter und normiert Kursbewegungen gegen den Marktkontext.
5. Überschreitet ein Signal die konfigurierte Schwelle, erzeugt es ein Überwachungs-Ereignis (Titel, Ereignistyp, Rohwerte, Zeitstempel) und übergibt es an die Analyse bestehender Titel (`[[analyse-pipelines]]`).
6. Es zählt die je Tag ausgelösten Ereignisse als Monitoring-Kennzahl (Alert-Fatigue-Leitplanke).

## Alternative Flows

### A1: Deaktivierte Anlageklasse mit offener Position
- Ist die Anlageklasse eines gehaltenen Titels per Feature-Toggle deaktiviert, bleibt die Überwachung dieses Titels trotzdem aktiv (keine neuen Käufe, aber „ein Toggle darf niemals dazu führen, dass eine gehaltene Position blind wird", → C-006).

### A2: Kein überwachungswürdiges Signal
- Liegt kein Signal über der Schwelle, entsteht kein Ereignis und es erfolgt keine Weitergabe an die Analyse.

### E1: Datenquellen-Abfrage liefert keine/veraltete Daten
- Fällt für einen Titel das Signal-Bündel aus oder ist es älter als das konfigurierte Frische-Fenster, wird der Titel als „nicht bewertbar" markiert und protokolliert; es wird **kein** Ereignis fabriziert (kein Verkaufsimpuls aus fehlenden Daten).

## Acceptance-Kriterien

- **AC1** — Für jeden im Depot gehaltenen Titel liest das Modul Titel, Anlageklasse, Strategie und die beim Kauf fixierten Exit-Regeln als Input; fehlt eines dieser Felder, wird der Titel als unvollständig protokolliert und nicht stillschweigend übersprungen.
- **AC2** — Je Titel wird genau eine Abfrage an die geteilte Datenquellen-Abfrage gestellt; das Modul betreibt keine eigene Preis-/Datenanbindung (DRY).
- **AC3** — Die je Titel überwachten Grössen werden anhand seiner Anlageklasse bestimmt: mindestens News-Katalysatoren, relativer Kurssturz, Sentiment-Kippen und Momentum-Verlust; für Anlageklasse 7 (Krypto) zusätzlich On-Chain-Abflüsse. Nicht zur Klasse passende Grössen werden nicht abgefragt.
- **AC4** — Der Keyword-/Ereignis-Filter lässt nur material relevante News durch. Default-Auslöser-Menge (provisorisch, konfigurierbar): „Insolvenz", „Hack", „Übernahme", „Gewinnwarnung", „Downgrade". Die Filter-Stichwortliste ist als Parameter konfigurierbar. Duplikate desselben Ereignisses werden entdoppelt.
- **AC5** — Kursbewegungen werden marktkontext-normiert bewertet: Ein Kurssturz wird relativ zur gleichzeitigen Marktbewegung beurteilt, nicht am Absolutwert (−10 % an einem −8 %-Markttag löst nicht dieselbe Bewertung aus wie −10 % an einem flachen Tag).
- **AC6** — Überschreitet ein Signal die Schwelle, erzeugt das Modul ein Überwachungs-Ereignis mit Titel, Ereignistyp, auslösenden Rohwerten und Zeitstempel und übergibt es an die Analyse bestehender Titel. Das Modul trifft dabei selbst keinen Kauf-/Verkaufs-Entscheid (AC deckt „Ereignis → Weitergabe, kein eigener Verkaufs-Entscheid").
- **AC7** — Die Anzahl erzeugter Ereignisse pro Tag wird als Monitoring-Kennzahl geführt; überschreitet sie den konfigurierten Schwellwert (Default provisorisch: 10 Ereignisse/Tag), wird dies als „zu sensibel" signalisiert (Alert-Fatigue-Leitplanke). Der Schwellwert ist konfigurierbar.
- **AC8** — Ist die Anlageklasse eines gehaltenen Titels deaktiviert, bleibt seine Überwachung aktiv (deckt A1).
- **AC9** — Fehlt oder veraltet das Signal-Bündel eines Titels über das konfigurierte Frische-Fenster hinaus, wird der Titel als „nicht bewertbar" protokolliert und es wird kein Ereignis erzeugt (deckt E1).

> **Traceability:** Jeder Test trägt das kanonische Trace-Tag `@trace depot-ueberwachung#AC<n>`.

## Verträge

- **Input (je gehaltenem Titel, aus dem Depotmodul):** `{ titel_id, anlageklasse (1–11), strategie, exit_regeln, einstand?, hoch_seit_kauf? }`.
- **Ausgehende Abfrage (an `[[datenquellen-abfrage]]`):** Liste der Titel-Identitäten mit Anlageklassen-Tag; Antwort ist das einheitliche Signal-Bündel je Titel (News, Kurs relativ zum Markt, Sentiment, Momentum, Liquidität, Volatilität; Krypto zusätzlich On-Chain-Abflüsse).
- **Output (Überwachungs-Ereignis, an `[[analyse-pipelines]]` / Analyse bestehende Titel):** `{ titel_id, ereignistyp, rohwerte, zeitstempel, quellen_id }`.
- **Monitoring-Kennzahl:** `ereignisse_pro_tag` (Zählwert) + Flag `zu_sensibel` bei Überschreitung des Schwellwerts.
- **Konfiguration:** Keyword-Liste, Ereignistyp-Schwellen je Anlageklasse, Prüffrequenz je Titel/Klasse, Alert-Tages-Schwellwert (Default 10), Frische-Fenster.

## Edge-Cases & Fehlerverhalten

- Mehrere Signale desselben Titels im selben Zyklus werden zu einem Ereignis je Ereignistyp gebündelt (keine Doppel-Weitergabe).
- Marktkontext-Normierung braucht einen Marktreferenz-Wert; fehlt dieser, wird konservativ auf Absolut-Bewertung zurückgefallen und dies protokolliert.
- Ein Überwachungs-Ereignis bedeutet „aufpassen und prüfen", nicht „sofort verkaufen" — die Weitergabe darf keinen Verkauf auslösen.

## NFRs

- Prüffrequenz je Anlageklasse konfigurierbar (kontinuierlich bis gebündelt, z. B. nach Börsenschluss), ohne die Rate-Limits der Datenquellen zu verletzen (Frequenzsteuerung liegt im Socket/der Datenquellen-Abfrage).

## Nicht-Ziele

- Keine Kandidatensuche nach **neuen** Titeln (das ist `[[suchkriteria]]`).
- Keine Exit-Entscheidung und keine Order-Erzeugung (nachgelagert: Analyse bestehende Titel → Exit-Sizing).
- Keine eigene Score-Berechnung.

## Abhängigkeiten

- `[[datenquellen-abfrage]]` (geteilte Abfrage; liefert Signal-Bündel)
- `[[analyse-pipelines]]` (Analyse bestehende Titel; Empfänger der Ereignisse)
- Depotmodul (liefert gehaltene Titel + Strategie + Exit-Regeln)
- Anlageklassen-Konfiguration / Feature-Toggles (← C-006)
