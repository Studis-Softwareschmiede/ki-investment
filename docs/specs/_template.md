---
id: <feature-slug>          # stabile Spec-ID, kebab-case, z.B. "user-login"
title: <Feature-Titel>
status: draft               # draft | active | superseded — genau diese drei Werte gültig; "approved" ist KEIN gültiger Status (Synonym-Drift für "active", siehe docs/specs/spec-status-lifecycle.md)
version: 1
spec_format: use-case-2.0   # aktuelle Standard-Version dieser Vorlage (offizielle Methodik-Bezeichnung, kein interner Zähler). requirement übernimmt diesen Wert 1:1 beim Anlegen neuer Specs. /agent-flow:reconcile Stufe 1 vergleicht den spec_format-Stempel jeder Spec gegen diesen Vorlagen-Wert, um veraltete/fehlende Form zu erkennen (docs/architecture/reconcile-subsystem.md §3, §8).
area: <bereich-id>          # Pflicht für NEUE Specs: kebab-case-id eines Eintrags in board/areas.yaml (docs/specs/board-areas.md AC6). Bestehende Specs ohne area bleiben gültig bis zur Migration — nicht rückwirkend nachtragen. Zuordnung + Stempelung übernimmt requirement (docs/specs/requirement-area-intake.md).
---

# Spec: <Feature-Titel>  (`<feature-slug>`)

> **Schicht 3 von 3.** Testbares **Verhalten + Verträge**, sprach-/paradigma-unabhängig (Intent, keine Idiome/Klassen).
> **Source of Truth** für `coder` (baut daraus), `tester` (testet die Acceptance-Kriterien + Coverage-Gate), `reviewer` (prüft den Diff dagegen — hartes Drift-Gate).
> **Struktur (Use-Case-2.0-Hybrid):** Die **Flows** (Main/Alternative) sind die *Herleitung* und **optional** — nur bei verzweigungsreichem Verhalten. Die **Acceptance-Kriterien** sind der *Pflicht-Vertrag* und werden aus den Flows abgeleitet. Geschäftsregeln werden NICHT hier definiert, sondern in `architecture.md` (Verhalten) / `data-model.md` (Validierung) als `BR-NNN` und hier nur **referenziert**.
> **Diese Vorlage ist aktuell auf `spec_format: use-case-2.0`** (siehe Frontmatter oben) — die offizielle Bezeichnung des angewandten Spec-Standards. Der `/agent-flow:reconcile`-Button (Stufe 1) vergleicht den `spec_format`-Stempel jeder bestehenden Spec gegen diesen Vorlagen-Wert, um veraltete oder fehlende Form zu erkennen und zu konvertieren.

## Zweck
<1–2 Sätze: was dieses Feature leistet und warum.>

## Main Success Scenario   <!-- OPTIONAL — nur bei verzweigungsreichem Verhalten; bei simplen Features weglassen -->
<Der Happy Path als nummerierte Schritte (Akteur-Sicht, ohne Implementierung).>
1. <…>
2. <…>
3. <…>

## Alternative Flows   <!-- OPTIONAL — die Verzweigungen & Fehlerpfade, die eine flache AC-Liste übersieht -->
### A1: <Bedingung / alternativer Erfolgspfad>
- <Schritte / Abweichung vom Main Scenario>

### E1: <Fehlerfall>
- <erwartetes Fehlerverhalten / Status>

## Acceptance-Kriterien
<Nummeriert, **testbar** — der Vertrag für `coder` + `tester`. Aus den Flows abgeleitet (jeder relevante Alt-/Fehlerpfad ⇒ eine AC). Board-Items referenzieren diese Nummern (z.B. „implements AC1–AC3"). AC-IDs sind **stabil** (nicht umnummerieren — neue AC anhängen). Verweise auf Geschäftsregeln via `(→ BR-NNN)`.>

- **AC1** — <überprüfbare Bedingung> <!-- z.B. (→ BR-002) wenn eine Geschäftsregel geprüft wird -->
- **AC2** — <…>
- **AC3** — <deckt A1 / E1> <!-- jeder benannte Alt-/Fehlerpfad sollte als AC auftauchen -->

> **Traceability:** Jeder Test trägt das kanonische Trace-Tag `@trace <feature-slug>#AC<n>[,BR-NNN]`
> gemäss `knowledge/<lang>.md` → `## Spec-Tagging`. Der `tester` rechnet das Coverage-Gate
> (jede genannte AC + jede referenzierte BR ≥ 1 deckender Test). Details: `docs/architecture/traceability-subsystem.md`.

## Verträge
<Inputs/Outputs · API-Endpunkte (Methode, Pfad, Request/Response) · Daten-Schema/Felder. Sprach-neutral.>

## Edge-Cases & Fehlerverhalten
<Grenzfälle, Fehlerpfade, erwartete Fehler-/Statuscodes. (Bei genutzten Alternative Flows hier nur ergänzen, was dort nicht steht.)>

## NFRs
<Feature-spezifische nicht-funktionale Anforderungen (Performance/Security/A11y), soweit relevant.>

## Nicht-Ziele
<bewusst ausgeschlossen.>

## Abhängigkeiten
<andere Specs (`[[feature-slug]]`) / externe Dienste · referenzierte Geschäftsregeln (`BR-NNN` aus `architecture.md`/`data-model.md`).>
