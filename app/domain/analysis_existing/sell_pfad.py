"""Sell-Pfad — Analyse bestehende Titel (S-034, Spec
`docs/specs/analyse-pipelines.md`, architecture.md §5.3, BR-011/BR-012).

`bewerte_bestehenden_titel` deckt Alternative Flow A1 der Spec ("Analyse
bestehende Titel — Wiederbewertung"):

- **AC5** — bewertet ausschliesslich gegen die beim Kauf fixierten
  Exit-Regeln des Titels; verhandelt weder Kaufschwelle noch These neu
  (BR-011, "kein moving the goalposts"). Strukturell abgesichert: diese
  Funktion nimmt weder Kategoriegewichte noch eine Score-Schwelle entgegen
  und ruft keine Buy-Pfad-/Score-Engine-Funktion auf — sie kann daher nie
  eine Kaufschwelle neu verhandeln. Die Leitfrage "Würden wir die Position
  heute kaufen, wenn wir sie nicht hielten?" ist als Entscheidungsregel
  abgebildet: ein `news_katalysator`-Ereignis, dessen Text die feste
  Thesis-Bruch-Enum trifft (AC7), beantwortet die Leitfrage klar mit
  "nein" (Hard-Exit); jedes andere Ereignis (bereits als "material
  relevant"/schwellenüberschreitend von `[[depot-ueberwachung]]`
  weitergereicht) beantwortet sie nicht eindeutig — es bleibt bei
  "Verschlechterung, aber keine Katastrophe" (Soft-Exit).
- **AC6** — jedes eingehende `UeberwachungsEreignis` erzeugt ein
  `SellSignal` mit Dringlichkeitsstufe. Da `[[depot-ueberwachung]]` (AC6,
  A2 der dortigen Spec) ein Ereignis bereits ausschliesslich bei
  Schwellenüberschreitung weiterreicht ("kein Signal über der Schwelle ->
  kein Ereignis"), ist die Exit-Bedingung an dieser Stelle der Pipeline
  bereits erfüllt — diese Funktion liefert daher nie `None`, sondern
  ausschliesslich die Dringlichkeits-Klassifikation (AC7).
- **AC7** — Dringlichkeit **Hard-Exit** (`"hard"`), wenn die These
  fundamental gebrochen ist: ein `news_katalysator`-Ereignis, dessen Text
  mindestens eines der Katastrophen-Stichworte (`DEFAULT_KATASTROPHEN_
  KEYWORDS` — Hack, Betrug, Delisting, Insolvenz) enthält. Sonst
  **Soft-Exit** (`"soft"`), "Verschlechterung ohne Katastrophe". Die
  Katastrophen-Enum ist laut Spec-Edge-Case "Thesis-Bruch-
  Operationalisierung (offen)" der **provisorische Default** — die
  konkrete Operationalisierung bleibt konfigurierbar (Parameter
  `katastrophen_keywords`), analog zu `DEFAULT_EREIGNIS_KEYWORDS`
  (`app.contracts.depot_ueberwachung`).

**Scope-Abgrenzung zu S-052 (AC8-AC10, `depends: S-034`):** die
numerischen/zeitbasierten Stop-Trigger-Typen (Drawdown-Trigger ggü.
Hoch/Einstand, ATR-Trailing je Strategie, Time-Box-Ablauf) benötigen
Preis-/ATR-/Zeit-Daten (`einstand`, `hoch_seit_kauf`, `exit_regeln
.stop_typ`/`.atr_multiplikator`/`.time_box`) und sind explizit NICHT Teil
dieser Story (S-052 implementiert AC8-AC10 separat, `depends: S-034`).
Diese Funktion liest daher bewusst KEINE `ExitRegelnBestand`-Felder (die
Katastrophen-Klassifikation ist laut obigem Edge-Case unabhängig von der
positions-individuellen `thesis_invalidation`-Freitext-Angabe) — alle
Nicht-News-Ereignistypen (`relativer_kurssturz`, `sentiment_kippen`,
`momentum_verlust`, `on_chain_abfluss`) gelten hier einheitlich als
"Verschlechterung ohne Katastrophe" (Soft-Exit), ohne Preis-/ATR-Vergleich.

Reiner Domain-Kern (architecture.md §4 P1/P3): keine I/O, kein
SQLAlchemy, kein Order-Ausführungspfad (F-015, Nicht-Ziel dieser Story) —
`bewerte_bestehenden_titel` liefert ausschliesslich ein `SellSignal`-DTO."""

from __future__ import annotations

from collections.abc import Sequence

from app.contracts.analyse_pipelines import Dringlichkeit, SellSignal
from app.contracts.depot_ueberwachung import UeberwachungsEreignis

#: AC7, Edge-Case "Thesis-Bruch-Operationalisierung (offen)": provisorischer
#: Default für die Enum, die eine `news_katalysator`-Meldung als
#: fundamentalen Thesis-Bruch (Hard-Exit) statt blosser Verschlechterung
#: (Soft-Exit) markiert.
DEFAULT_KATASTROPHEN_KEYWORDS: tuple[str, ...] = ("Hack", "Betrug", "Delisting", "Insolvenz")


def _ist_thesis_bruch(
    ereignis: UeberwachungsEreignis, katastrophen_keywords: Sequence[str]
) -> bool:
    """AC7: `True`, wenn `ereignis` ein `news_katalysator`-Ereignis ist,
    dessen Text (case-insensitiv, Teilstring, analog
    `app.domain.depot_ueberwachung.ereignis_filter.filtere_relevante_news`)
    mindestens eines der `katastrophen_keywords` enthält."""
    if ereignis.ereignistyp != "news_katalysator":
        return False
    texte_normiert = ereignis.rohwerte.get("texte", "").casefold()
    keywords_normiert = [keyword.casefold() for keyword in katastrophen_keywords if keyword.strip()]
    return any(keyword in texte_normiert for keyword in keywords_normiert)


def bewerte_bestehenden_titel(
    ereignis: UeberwachungsEreignis,
    *,
    katastrophen_keywords: Sequence[str] = DEFAULT_KATASTROPHEN_KEYWORDS,
) -> SellSignal:
    """Bewertet ein Überwachungs-Ereignis eines gehaltenen Titels und
    liefert ein `SellSignal` (AC5-AC7).

    `ereignis` MUSS bereits die Schwellenprüfung der Depot-Überwachung
    durchlaufen haben (`app.domain.depot_ueberwachung.ereignis_erzeugung
    .erzeuge_ueberwachungsereignisse`) — diese Funktion trifft selbst keine
    weitere Schwellenentscheidung (AC6: jedes übergebene Ereignis erzeugt
    ein Sell-Signal). `zeitstempel`/`rohwerte` werden unverändert aus
    `ereignis` übernommen (deterministisch, keine Systemzeit-Abhängigkeit,
    NFR der Spec)."""
    dringlichkeit: Dringlichkeit = (
        "hard" if _ist_thesis_bruch(ereignis, katastrophen_keywords) else "soft"
    )
    return SellSignal(
        titel_id=ereignis.titel_id,
        dringlichkeit=dringlichkeit,
        ausloeser=ereignis.ereignistyp,
        rohwerte=dict(ereignis.rohwerte),
        zeitstempel=ereignis.zeitstempel,
    )


__all__ = ["DEFAULT_KATASTROPHEN_KEYWORDS", "bewerte_bestehenden_titel"]
