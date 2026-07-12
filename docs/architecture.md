# Detailkonzept / Architektur — ki-investment

> **Schicht 2 von 3.** Das **WIE konzeptionell** — logisch, sprach-/paradigma-unabhängig (Komponenten/Flows/Zustände, keine Idiome/Klassen). Geschrieben vom `architekt`. Bindend für den `coder`; Architektur-Konformität ist Review-Kriterium.

## Domänenmodell
<Kern-Entitäten/Begriffe (siehe `glossary.md`) + ihre Beziehungen, sprach-neutral.>

## Geschäftsregeln (BR-NNN)
<Zentrale, feature-übergreifende Domäneninvarianten. **Hier lebt jede Regel EINMAL**; Specs referenzieren sie via `(→ BR-NNN)`, Tests taggen sie (`#BR-NNN`) — kein Duplizieren in einzelnen Specs.
ID-Schema: `BR-NNN` (3-stellig, fortlaufend, **stabil** — nicht umnummerieren). Rein **verhaltensbezogene** Regeln hier; **datenvalidierende** Regeln stehen in `data-model.md` (gleicher `BR-NNN`-Namensraum, fortlaufend über beide Dateien). Abgrenzung: `BR-NNN` = Projekt-Geschäftsregel ≠ `lang/R<NN>` = Fabrik-Qualitätsregel der Knowledge Packs.>

### BR-001: <Kurztitel>
<Eine prüfbare Regel in einem Satz. Optional: Begründung / Quelle (z.B. fachliche Vorgabe).>

### BR-002: <Kurztitel>
<…>

## Komponenten
<Module/Komponenten · Verantwortlichkeit · Boundaries (was kennt was).>

## Kern-Flows
<Wichtigste Abläufe Schritt-für-Schritt (ohne Code).>

## Zustände
<Relevante Zustandsmaschinen / Lebenszyklen.>

## Externe Schnittstellen
<APIs / Dienste / Datenquellen + Vertragspunkte.>

## NFRs
<Performance, Sicherheit, A11y, Verfügbarkeit — als prüfbare Vorgaben, soweit relevant.>

## Entscheidungen (ADR)
<Eine Zeile/Block je Architektur-Entscheidung — ID · Datum · Entscheidung · Begründung · verworfene Alternativen.>
