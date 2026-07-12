# ki-investment

KI-gestützte vollautomatische Investment-App für Semi-Profis: scannt Nachrichten und Marktdaten,
bewertet Titel über 11 Anlageklassen und 5 Analysekategorien (Score 0–10) und trifft
Kauf-/Verkaufsentscheide — hybrid autonom oder mit Nutzer-Benachrichtigung.

- Stack: Python 3.13 + FastAPI (uv), Postgres (alembic), Redis (Scheduler/Cache)
- Durable Source of Truth: `docs/` (concept, architecture, specs, data-model)
- Board: file-basiert unter `board/` (Single Writer: /flow)
- Konzept-Quelle: Obsidian-Vault `300 Projekte/KI Investment` (via /agent-flow:from-notes)

## Kommunikation mit dem Owner

Diese Vorgaben gelten für die **Haupt-Session im Dialog mit dem Owner** — nicht für die Arbeits-Agenten (coder/reviewer/tester/…), die ihren Handoff-Verträgen folgen.

- **Ergebnis zuerst.** 1–2 Sätze in Alltagssprache, was passiert ist bzw. was empfohlen wird. Kein Status-Dump aller berührten Dateien.
- **Wenig Fachjargon.** Kürzel/IDs (z. B. AC-Nummern, K3, Datei-Pfade) nur wenn nötig — und beim ersten Mal kurz erklären. Lieber ein Bild als ein Fachbegriff.
- **3-Schichten-Antwort:**
  1. **Ergebnis** — immer, ohne Jargon.
  2. **Begründung** — nur wenn nötig, kurze Stichpunkte in Alltagssprache.
  3. **Technische Details** (Pfade, Kürzel, Zeilennummern) — nur auf Nachfrage oder bei echtem Risiko.
- **Länge an die Frage koppeln.** Kurze Frage → kurze Antwort.
- **Steuerwörter des Owners** (sofort befolgen):
  - `kurz` → nur Schicht 1.
  - `erklär` → Schicht 1 + 2 in Alltagssprache.
  - `technisch` → volle Details mit Pfaden/Kürzeln.

## Parallelbetrieb: mehrere Cloud-Sessions

Der Owner arbeitet an diesem Repo häufig mit mehreren Cloud-Sessions gleichzeitig (z. B. um mehrere Anforderungen parallel einzubringen). Fremde, session-fremde Änderungen im Working Tree/Board sind normal — kein Hinweis an den Owner nötig, solange keine eigene Arbeit dadurch verloren geht.

**Pflicht: eigener Branch UND eigener Worktree.** Ein reiner Branch-Wechsel reicht NICHT — er tauscht die Dateien im geteilten Hauptordner auch für jede andere dort aktive Session aus. Bevor eine Session in diesem Repo schreibend tätig wird (Board-Dateien, Specs, Code) und nicht sicher ausschließen kann, dass sie die einzige aktive Session ist, MUSS sie zuerst `EnterWorktree` aufrufen (eigener Ordner unter `.claude/worktrees/`, eigener Branch, gleiche Git-Historie wie der Hauptordner). Am Ende der Session: Änderungen committen + pushen, danach `ExitWorktree` (`action: "remove"`, sobald nichts mehr daraus gebraucht wird).

**Warum:** `git checkout`/`reset`/`clean` im Hauptordner wirkt sich auf ALLE dort aktiven Prozesse aus — auch auf noch nicht committete Änderungen einer anderen Session. Das führt zu stillem Datenverlust statt zu einem sichtbaren Konflikt. *(Vorfall 2026-07-02, dev-gui: ein `/requirement`-Lauf verlor zweimal frisch angelegte Board-Items, weil eine parallele Headless-Flow-Session im selben Hauptordner reset/clean ausführte.)*

Ausnahme: rein lesende Sessions (nur ansehen, keine Schreiboperation geplant) können im Hauptordner bleiben.
