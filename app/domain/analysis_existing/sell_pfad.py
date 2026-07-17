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

**S-052 (AC8-AC10, `depends: S-034`)** ergänzt die numerischen/zeitbasierten
Stop-Trigger-Typen, die S-034 bewusst ausgeklammert hatte (Preis-/ATR-/
Zeit-Daten `einstand`, `hoch_seit_kauf`, `exit_regeln.stop_typ`/
`.atr_multiplikator`/`.time_box`, siehe `app.contracts.analyse_pipelines
.ExitTriggerKontext`):

- **AC8 (Drawdown-Trigger):** löst eine Wiederbewertung (Review, Soft-Exit)
  aus, wenn der Kurs 20% vom Hoch seit Kauf ODER 10% vom Einstand gefallen
  ist UND der Titel gleichzeitig ggü. dem Markt underperformt (marktkontext-
  normiert, analog `app.domain.depot_ueberwachung.marktkontext
  .normiere_kursbewegung`, AC5 dortiger Spec) — kein blinder Stop, sondern
  eine Review-Auslösung.
- **AC9 (Stop-Typ je Strategie):** der beim Kauf fixierte `stop_typ`
  (`ExitRegelnBestand`, bereits strategie-abhängig von S-038 bestimmt)
  entscheidet den numerischen Prüfmechanismus: `"atr_trailing"`
  (Momentum) prüft den aktuellen Kurs gegen `hoch_seit_kauf - atr_wert *
  atr_multiplikator`; `"fix_pct"` (Buy-and-Hold) gegen `einstand * (1 -
  stop_loss_pct)`; `"fundamental"` (Value, kein reiner Kurs-Stop) und
  `"keiner"` lösen nie einen numerischen Kurs-Stop aus.
- **AC10 (Time-Box):** löst eine Review aus, sobald die seit Kauf/letzter
  Bewegung verstrichene Zeit (`position_alter`) die konfigurierte
  `time_box`-Frist erreicht oder überschreitet; `time_box=None` (keine
  Frist konfiguriert, z.B. Index/Buy-and-Hold, A2 der Exit-Regel-Spec)
  löst nie aus.

Diese drei Trigger sind additiv über den optionalen `exit_kontext`-
Parameter angebunden (`ExitTriggerKontext | None`): fehlt er (S-034-
Cold-Start, kein Aufrufer liefert bislang die Depot-Werte), bleibt das
bisherige Verhalten unverändert (jedes bereits schwellenwertete Ereignis
erzeugt ein Soft-Exit-Signal, AC6/AC7 S-034). Ist er gesetzt, entscheiden
ausschliesslich die drei AC8-AC10-Trigger, ob ein Sell-Signal entsteht —
liegt keiner davon vor, liefert die Funktion `None` ("aufpassen und
prüfen", nicht "sofort verkaufen", Edge-Case `depot-ueberwachung.md`).
Ein fundamentaler Thesis-Bruch (AC7) bleibt davon unberührt: er erzeugt
immer ein Hard-Exit-Signal, unabhängig vom `exit_kontext`.

Reiner Domain-Kern (architecture.md §4 P1/P3): keine I/O, kein
SQLAlchemy, kein Order-Ausführungspfad (F-015, Nicht-Ziel dieser Story) —
`bewerte_bestehenden_titel` liefert ausschliesslich ein `SellSignal`-DTO
(oder `None`, S-052)."""

from __future__ import annotations

from collections.abc import Sequence
from decimal import Decimal

from app.contracts.analyse_pipelines import Dringlichkeit, ExitTriggerKontext, SellSignal
from app.contracts.depot_ueberwachung import UeberwachungsEreignis
from app.domain.depot_ueberwachung.marktkontext import normiere_kursbewegung

#: AC7, Edge-Case "Thesis-Bruch-Operationalisierung (offen)": provisorischer
#: Default für die Enum, die eine `news_katalysator`-Meldung als
#: fundamentalen Thesis-Bruch (Hard-Exit) statt blosser Verschlechterung
#: (Soft-Exit) markiert.
DEFAULT_KATASTROPHEN_KEYWORDS: tuple[str, ...] = ("Hack", "Betrug", "Delisting", "Insolvenz")

#: AC8, Edge-Case "Schwellen sind konfigurierbar": provisorischer Default —
#: 20% Fall vom Hoch seit Kauf.
DEFAULT_DRAWDOWN_HOCH_SCHWELLE: Decimal = Decimal("0.20")

#: AC8, Edge-Case "Schwellen sind konfigurierbar": provisorischer Default —
#: 10% Fall vom Einstand.
DEFAULT_DRAWDOWN_EINSTAND_SCHWELLE: Decimal = Decimal("0.10")


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


def _relativer_fall(referenz: Decimal, aktueller_kurs: Decimal) -> Decimal:
    """AC8: relativer Kursfall gegenüber `referenz` (Hoch seit Kauf oder
    Einstand). `referenz <= 0` ist strukturell unmöglich (Kurs/Einstand
    sind stets positiv) — liefert dann konservativ `0` (kein Fall) statt
    einer Division durch Null."""
    if referenz <= 0:
        return Decimal("0")
    return (referenz - aktueller_kurs) / referenz


def _ist_drawdown_getriggert(
    kontext: ExitTriggerKontext,
    *,
    drawdown_hoch_schwelle: Decimal,
    drawdown_einstand_schwelle: Decimal,
) -> bool:
    """AC8: `True`, wenn der Kurs mindestens `drawdown_hoch_schwelle` vom
    Hoch seit Kauf ODER mindestens `drawdown_einstand_schwelle` vom
    Einstand gefallen ist (Schwelle exakt erreicht zählt bereits als
    ausgelöst, `>=`) UND der Titel gleichzeitig ggü. dem Markt
    underperformt (marktkontext-normierte Bewegung negativ, analog AC5
    `depot-ueberwachung`; fehlt der Marktreferenzwert, fällt
    `normiere_kursbewegung` konservativ auf den Absolutwert zurück)."""
    fall_vom_hoch = _relativer_fall(kontext.hoch_seit_kauf, kontext.aktueller_kurs)
    fall_vom_einstand = _relativer_fall(kontext.einstand, kontext.aktueller_kurs)
    kurs_gefallen = (
        fall_vom_hoch >= drawdown_hoch_schwelle or fall_vom_einstand >= drawdown_einstand_schwelle
    )
    if not kurs_gefallen:
        return False
    normiert = normiere_kursbewegung(kontext.titel_bewegung_pct, kontext.markt_bewegung_pct)
    return normiert.normierte_bewegung < 0


def _ist_stop_getriggert(kontext: ExitTriggerKontext) -> bool:
    """AC9: prüft den Kurs gegen den beim Kauf fixierten `stop_typ` (bereits
    strategie-abhängig bestimmt, S-038) — `"atr_trailing"` (Momentum)
    gegen den ATR-Trailing-Stop-Niveau, `"fix_pct"` (Buy-and-Hold) gegen
    den prozentualen Einstands-Stop; `"fundamental"` (Value, kein reiner
    Kurs-Stop) und `"keiner"` lösen nie einen numerischen Stop aus. Fehlen
    die für den Mechanismus nötigen Werte (`atr_wert`/`atr_multiplikator`
    bzw. `stop_loss_pct`), gilt der Stop als (noch) nicht auslösbar —
    analog zum `stop_unbestimmt`-Edge-Case aus `app.db.exit_regel_ableitung`."""
    if kontext.stop_typ == "atr_trailing":
        if kontext.atr_wert is None or kontext.atr_multiplikator is None:
            return False
        stop_niveau = kontext.hoch_seit_kauf - (kontext.atr_wert * kontext.atr_multiplikator)
        return kontext.aktueller_kurs <= stop_niveau
    if kontext.stop_typ == "fix_pct":
        if kontext.stop_loss_pct is None:
            return False
        stop_niveau = kontext.einstand * (Decimal("1") - kontext.stop_loss_pct)
        return kontext.aktueller_kurs <= stop_niveau
    return False


def _ist_time_box_getriggert(kontext: ExitTriggerKontext) -> bool:
    """AC10: `True`, sobald die seit Kauf/letzter Bewegung verstrichene
    Zeit (`position_alter`) die konfigurierte `time_box`-Frist erreicht
    oder überschreitet (`>=`). `time_box=None` (keine Frist konfiguriert,
    z.B. Index/Buy-and-Hold, A2 `strategie-exit-regeln.md`) löst nie aus."""
    if kontext.time_box is None:
        return False
    return kontext.position_alter >= kontext.time_box


def _ermittle_regel_ausloeser(
    kontext: ExitTriggerKontext,
    *,
    drawdown_hoch_schwelle: Decimal,
    drawdown_einstand_schwelle: Decimal,
) -> str | None:
    """AC8-AC10: liefert den Namen des zuerst zutreffenden Exit-Triggers
    (Drawdown vor Stop-Typ vor Time-Box — keiner der drei Trigger schliesst
    die anderen aus, die Reihenfolge bestimmt nur den `ausloeser`-Namen bei
    mehreren gleichzeitig erfüllten Bedingungen) oder `None`, wenn keiner
    zutrifft ("aufpassen und prüfen", kein Exit)."""
    if _ist_drawdown_getriggert(
        kontext,
        drawdown_hoch_schwelle=drawdown_hoch_schwelle,
        drawdown_einstand_schwelle=drawdown_einstand_schwelle,
    ):
        return "drawdown"
    if _ist_stop_getriggert(kontext):
        return f"stop_{kontext.stop_typ}"
    if _ist_time_box_getriggert(kontext):
        return "time_box"
    return None


def bewerte_bestehenden_titel(
    ereignis: UeberwachungsEreignis,
    *,
    katastrophen_keywords: Sequence[str] = DEFAULT_KATASTROPHEN_KEYWORDS,
    exit_kontext: ExitTriggerKontext | None = None,
    drawdown_hoch_schwelle: Decimal = DEFAULT_DRAWDOWN_HOCH_SCHWELLE,
    drawdown_einstand_schwelle: Decimal = DEFAULT_DRAWDOWN_EINSTAND_SCHWELLE,
) -> SellSignal | None:
    """Bewertet ein Überwachungs-Ereignis eines gehaltenen Titels und
    liefert ein `SellSignal` (AC5-AC10) oder `None` (S-052: kein Exit
    möglich — "aufpassen und prüfen", nicht "sofort verkaufen").

    `ereignis` MUSS bereits die Schwellenprüfung der Depot-Überwachung
    durchlaufen haben (`app.domain.depot_ueberwachung.ereignis_erzeugung
    .erzeuge_ueberwachungsereignisse`) — diese Funktion trifft selbst keine
    weitere Schwellenentscheidung darüber, OB ein Ereignis relevant ist,
    sondern (S-052) darüber, OB die Depot-Exit-Regeln eine Wiederbewertung
    (Review) verlangen.

    Ein fundamentaler Thesis-Bruch (AC7, News-Katastrophen-Enum) erzeugt
    immer ein Hard-Exit-Signal, unabhängig von `exit_kontext`. Fehlt
    `exit_kontext` sonst (`None`, S-034-Cold-Start), bleibt das bisherige
    Verhalten unverändert: jedes übergebene Ereignis erzeugt ein Soft-Exit-
    Signal (AC6/AC7 S-034). Ist `exit_kontext` gesetzt, entscheiden
    ausschliesslich die drei AC8-AC10-Trigger (Drawdown, Stop-Typ je
    Strategie, Time-Box) — liegt keiner davon vor, liefert die Funktion
    `None`. `zeitstempel`/`rohwerte` werden in jedem Fall unverändert aus
    `ereignis` übernommen (deterministisch, keine Systemzeit-Abhängigkeit,
    NFR der Spec)."""
    if _ist_thesis_bruch(ereignis, katastrophen_keywords):
        return _erzeuge_signal(ereignis, "hard", ausloeser=ereignis.ereignistyp)
    if exit_kontext is None:
        return _erzeuge_signal(ereignis, "soft", ausloeser=ereignis.ereignistyp)
    ausloeser = _ermittle_regel_ausloeser(
        exit_kontext,
        drawdown_hoch_schwelle=drawdown_hoch_schwelle,
        drawdown_einstand_schwelle=drawdown_einstand_schwelle,
    )
    if ausloeser is None:
        return None
    return _erzeuge_signal(ereignis, "soft", ausloeser=ausloeser)


def _erzeuge_signal(
    ereignis: UeberwachungsEreignis, dringlichkeit: Dringlichkeit, *, ausloeser: str
) -> SellSignal:
    return SellSignal(
        titel_id=ereignis.titel_id,
        dringlichkeit=dringlichkeit,
        ausloeser=ausloeser,
        rohwerte=dict(ereignis.rohwerte),
        zeitstempel=ereignis.zeitstempel,
    )


__all__ = [
    "DEFAULT_DRAWDOWN_EINSTAND_SCHWELLE",
    "DEFAULT_DRAWDOWN_HOCH_SCHWELLE",
    "DEFAULT_KATASTROPHEN_KEYWORDS",
    "bewerte_bestehenden_titel",
]
