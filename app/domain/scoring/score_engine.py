"""Score-Engine — Berechnungskern des Analyse-Frameworks (C-007, S-009/S-010).

Reiner Domain-Kern (architecture.md §4 P1/P3): keine I/O, kein LLM, kein
FastAPI, kein SQLAlchemy. Deckt aus `docs/specs/analyse-framework.md` den
Berechnungskern dieser Storys:

- **AC1/AC2** — Kategorie-Score als Ranking-gewichtetes Mittel der
  vorhandenen Methodenscores: `Σ(Methodenscore × Ranking) / Σ(Ranking)`.
- **AC9** (deckt A2) — fehlende einzelne Methodenscores fließen nicht als 0
  ein, sondern werden aus Zähler/Nenner ausgeschlossen.
- **AC4** — Referenz-Verifikation der Formel (siehe Tests).
- **AC3** — Gesamtscore als gewichtete Summe der 5 Kategorie-Scores.
- **AC5/AC6** — Signal-Ableitung aus dem Gesamtscore nach (je Anlageklasse
  konfigurierbaren) Score-Schwellen.
- **AC7** — Risiko-Sanity-Cap: Kategorie-Score "Risiko & Quantitativ" < 3
  (Schwellwert konfigurierbar) deckelt ein rechnerisches KAUF/BEOBACHTEN
  auf HALTEN.
- **AC11** — reine Funktionen ohne Seiteneffekte, ohne Zeit-/Zufalls-
  abhängigkeit: identische Eingaben liefern identische Ergebnisse.

NICHT Teil dieser Story (Nicht-Ziele/Folge-Story S-011): die
No-Evidence-No-Trade-Skip-Entscheidung (AC8) und der Spinnennetz-Output
(AC10). `berechne_kategorie_score`/`berechne_kategorie_scores` liefern
dafür bereits den nötigen Hook: `None`, wenn eine Kategorie keine
verwertbare Evidenz hat (Edge-Cases der Spec).
"""

from __future__ import annotations

from collections.abc import Sequence

from app.contracts.analyse_framework import (
    KATEGORIE_NAMEN,
    KategorieEingabe,
    Kategoriegewichte,
    KategorieScores,
    MethodeEingabe,
    ScoreSchwellen,
    Signal,
)

#: NFR: Kategorie-Score und Gesamtscore sind auf 2 Dezimalstellen
#: reproduzierbar.
_PRAEZISION = 2

#: Verträge/AC2: gültiger Methodenscore-Bereich. Ein Wert außerhalb dieses
#: Bereichs ist laut Edge-Cases "ungültige Eingabe, wird nicht verrechnet".
_METHODENSCORE_MIN = 1
_METHODENSCORE_MAX = 10

#: Kategoriegewichte sind Prozentwerte 0–100 (siehe Kategoriegewichte-
#: Docstring) — die Gesamtscore-Summe normalisiert entsprechend.
_GEWICHT_NORMIERUNG = 100

#: AC7: Default-Schwellwert des Risiko-Sanity-Caps — unterhalb dieses
#: Risiko-Kategorie-Scores wird das Gesamtsignal auf höchstens HALTEN
#: gedeckelt. "Der Cap-Schwellwert 3 ist konfigurierbar" (AC7): Aufrufer
#: können `wende_risiko_sanity_cap_an(..., cap_schwelle=...)` mit einem
#: abweichenden Wert aufrufen.
_RISIKO_CAP_SCHWELLE_DEFAULT = 3.0

#: AC7: Signale, die der Sanity-Cap deckelt ("ein rechnerisches KAUF oder
#: BEOBACHTEN wird auf HALTEN gedeckelt, während REDUZIEREN und VERKAUF
#: unverändert bleiben").
_DURCH_SANITY_CAP_GEDECKELTE_SIGNALE = ("KAUF", "BEOBACHTEN")


def berechne_kategorie_score(methoden: Sequence[MethodeEingabe]) -> float | None:
    """AC1/AC2/AC9: `Σ(Methodenscore × Ranking) / Σ(Ranking)` über alle
    Methoden MIT vorhandenem, gültigem (1–10) Methodenscore.

    - Fehlende Methodenscores (`methodenscore is None`) fließen nicht ein
      und werden NICHT als 0 gewertet (AC9, deckt A2).
    - Ein Methodenscore außerhalb 1–10 ist eine ungültige Eingabe und wird
      ebenfalls nicht verrechnet (Edge-Cases der Spec).
    - Bleibt keine gültige Methode übrig — inklusive des Sonderfalls
      Σ(Ranking) = 0 über die gültige Teilmenge — gilt die Kategorie als
      ohne verwertbare Evidenz: Rückgabe `None` (Edge-Cases; die
      Entscheidung, einen Titel deswegen zu überspringen, ist AC8 und
      Nicht-Ziel dieser Story).
    """
    zaehler = 0.0
    nenner = 0.0
    for methode in methoden:
        score = methode.methodenscore
        if score is None:
            continue
        if not (_METHODENSCORE_MIN <= score <= _METHODENSCORE_MAX):
            continue
        zaehler += score * methode.ranking
        nenner += methode.ranking

    if nenner == 0:
        return None
    return round(zaehler / nenner, _PRAEZISION)


def berechne_kategorie_scores(kategorien: Sequence[KategorieEingabe]) -> KategorieScores:
    """Wendet `berechne_kategorie_score` je der 5 Analysekategorien an und
    liefert das Ergebnis in der Output-Form der Verträge
    (`kategorie_scores`). Für eine der 5 Kategorien, die in `kategorien`
    nicht vorkommt, wird ebenfalls `None` geliefert (keine Evidenz,
    gleichbedeutend mit einer vollständig leeren Methodenliste)."""
    methoden_je_kategorie = {eintrag.kategorie: eintrag.methoden for eintrag in kategorien}
    werte: dict[str, float | None] = {
        kategorie: berechne_kategorie_score(methoden_je_kategorie.get(kategorie, ()))
        for kategorie in KATEGORIE_NAMEN
    }
    return KategorieScores(**werte)


def berechne_gesamtscore(
    kategorie_scores: KategorieScores, kategoriegewichte: Kategoriegewichte
) -> float:
    """AC3: `Σ(Kategorie-Score × Kategoriegewicht der Klasse) / 100` über die
    5 Kategorien (Kategoriegewichte als Prozentwerte 0–100, Summe 100 % —
    validiert in [[anlageklassen-config]], nicht hier).

    Setzt voraus, dass ALLE 5 Kategorie-Scores vorhanden sind (kein
    `None`) — die No-Evidence-No-Trade-Skip-Entscheidung bei einer
    fehlenden Kategorie (AC8) liegt vor diesem Aufruf, in einer Folge-Story
    (S-011).

    Raises:
        ValueError: wenn mindestens eine Kategorie keinen Score hat
            (`None`) — der Aufrufer hätte den Titel vorher überspringen
            müssen (AC8).
    """
    summe = 0.0
    for kategorie in KATEGORIE_NAMEN:
        score = getattr(kategorie_scores, kategorie)
        if score is None:
            raise ValueError(
                f"Gesamtscore nicht berechenbar: Kategorie '{kategorie}' hat keinen "
                "Score (fehlende Evidenz — die No-Evidence-No-Trade-Entscheidung, "
                "AC8, muss vor diesem Aufruf getroffen werden)."
            )
        gewicht = getattr(kategoriegewichte, kategorie)
        summe += score * gewicht

    return round(summe / _GEWICHT_NORMIERUNG, _PRAEZISION)


def leite_signal_ab(gesamtscore: float, schwellen: ScoreSchwellen | None = None) -> Signal:
    """AC5/AC6: leitet aus dem Gesamtscore das Handlungssignal ab.

    Schwellen (Untergrenze inklusiv, AC5): ≥ `schwellen.kauf` → KAUF,
    ≥ `schwellen.beobachten` → BEOBACHTEN, ≥ `schwellen.halten` → HALTEN,
    ≥ `schwellen.reduzieren` → REDUZIEREN, sonst VERKAUF.

    `schwellen` ist optional (AC6): fehlt es, gelten die globalen
    AC5-Default-Schwellen (`ScoreSchwellen()`); für eine je Anlageklasse
    abweichende Konfiguration übergibt der Aufrufer eine `ScoreSchwellen`-
    Instanz mit den klassenspezifischen Werten (nicht gesetzte Felder
    fallen bereits auf DTO-Ebene auf den Default zurück, siehe
    `ScoreSchwellen`-Docstring).
    """
    aktive_schwellen = schwellen if schwellen is not None else ScoreSchwellen()

    if gesamtscore >= aktive_schwellen.kauf:
        return "KAUF"
    if gesamtscore >= aktive_schwellen.beobachten:
        return "BEOBACHTEN"
    if gesamtscore >= aktive_schwellen.halten:
        return "HALTEN"
    if gesamtscore >= aktive_schwellen.reduzieren:
        return "REDUZIEREN"
    return "VERKAUF"


def wende_risiko_sanity_cap_an(
    signal: Signal,
    risiko_score: float,
    cap_schwelle: float = _RISIKO_CAP_SCHWELLE_DEFAULT,
) -> tuple[Signal, bool]:
    """AC7: Risiko-Sanity-Cap (deckt A1).

    Ist `risiko_score` (Kategorie-Score "Risiko & Quantitativ") kleiner als
    `cap_schwelle` (Default 3, konfigurierbar), wird ein rechnerisches KAUF
    oder BEOBACHTEN auf HALTEN gedeckelt — REDUZIEREN und VERKAUF bleiben
    unverändert. Liefert das (ggf. gedeckelte) Signal sowie das
    `sanity_cap_angewendet`-Flag der Verträge.

    `risiko_score` ist bewusst nicht optional: der Sanity-Cap greift erst
    nach `berechne_gesamtscore`, das bereits voraussetzt, dass alle 5
    Kategorie-Scores (inkl. Risiko) vorhanden sind — eine fehlende
    Risiko-Kategorie hätte den Titel vorher über No-Evidence-No-Trade
    (AC8, Nicht-Ziel dieser Story) aus dem Flow genommen.
    """
    if risiko_score < cap_schwelle and signal in _DURCH_SANITY_CAP_GEDECKELTE_SIGNALE:
        return "HALTEN", True
    return signal, False
