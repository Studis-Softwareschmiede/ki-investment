"""Ereignis-Erzeugung & Weitergabe (Story S-033, Spec
`docs/specs/depot-ueberwachung.md` AC6, Main-Success-Scenario Schritt 5:
"Überschreitet ein Signal die konfigurierte Schwelle, erzeugt es ein
Überwachungs-Ereignis ... und übergibt es an die Analyse bestehender
Titel").

Reiner Domain-Kern (architecture.md §4 P1/P3): keine I/O, kein
SQLAlchemy, kein Kauf-/Verkaufs-Entscheid (AC6: "Das Modul trifft dabei
selbst keinen Kauf-/Verkaufs-Entscheid") — `erzeuge_ueberwachungsereignisse`
nimmt ausschliesslich reine Rohdaten entgegen und liefert ausschliesslich
`UeberwachungsEreignis`-DTOs zurück; es gibt keinen Aufruf einer Order-/
Positions-Funktion in diesem Modul. Die tatsächliche "Weitergabe" an die
Analyse bestehender Titel (`[[analyse-pipelines]]`, Sell-Pfad) ist noch
nicht gebaut (siehe `app.contracts.depot_ueberwachung.UeberwachungsEreignis`-
Docstring) — der zurückgelieferte Tupel ist der vollständige Output dieser
Story.

Kombiniert den Keyword-Filter (AC4, `ereignis_filter`) und die
Marktkontext-Normierung (AC5, `marktkontext`) mit den je Ereignistyp
konfigurierten Schwellen (Verträge "Konfiguration: ... Ereignistyp-
Schwellen je Anlageklasse", provisorisch klassenunabhängig einheitlich,
siehe `app.contracts.depot_ueberwachung.DEFAULT_EREIGNIS_SCHWELLEN`) zu
den Ereignistypen aus `app.domain.depot_ueberwachung.ueberwachte_groessen`.

Bündelung (Edge-Case "Mehrere Signale desselben Titels im selben Zyklus
werden zu einem Ereignis je Ereignistyp gebündelt"): pro `(titel_id,
ereignistyp)` entsteht höchstens EIN `UeberwachungsEreignis` je Aufruf —
mehrere relevante News desselben Titels werden zu einem einzigen
`news_katalysator`-Ereignis gebündelt (Rohwerte tragen Trefferzahl +
alle beitragenden Texte). Kein Signal über der Schwelle -> kein Ereignis
(A2)."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import datetime
from decimal import Decimal

from app.contracts.depot_ueberwachung import (
    DEFAULT_EREIGNIS_KEYWORDS,
    DEFAULT_EREIGNIS_SCHWELLEN,
    TitelSignalRohdaten,
    UeberwachungsEreignis,
)
from app.domain.depot_ueberwachung.ereignis_filter import filtere_relevante_news
from app.domain.depot_ueberwachung.marktkontext import normiere_kursbewegung


def erzeuge_ueberwachungsereignisse(
    rohdaten: Sequence[TitelSignalRohdaten],
    *,
    schwellen: Mapping[str, Decimal] | None = None,
    keywords: Sequence[str] = DEFAULT_EREIGNIS_KEYWORDS,
    jetzt: datetime,
) -> tuple[UeberwachungsEreignis, ...]:
    """AC6: liefert je Titel in `rohdaten` die Überwachungs-Ereignisse,
    für die mindestens ein Signal die konfigurierte Schwelle STRIKT
    überschreitet — News gegen den Keyword-Filter (AC4), Kursbewegung
    marktkontext-normiert (AC5, Betrag der Übertreibung ggü. dem Markt),
    Sentiment/Momentum/On-Chain gegen ihre je Ereignistyp konfigurierte
    Schwelle. `schwellen=None` bzw. fehlende Einzelwerte fallen auf
    `DEFAULT_EREIGNIS_SCHWELLEN` zurück (Edge-Case "Toleranz/Schwelle
    nicht konfiguriert" -> Default statt Codeänderung, Muster von
    `app.config.DEFAULT_TOLERANZEN`)."""
    aktive_schwellen = dict(DEFAULT_EREIGNIS_SCHWELLEN)
    if schwellen is not None:
        aktive_schwellen.update(schwellen)

    ereignisse: list[UeberwachungsEreignis] = []
    for titel in rohdaten:
        ereignisse.extend(_news_ereignis(titel, keywords=keywords, jetzt=jetzt))
        ereignisse.extend(
            _numerisches_ereignis(
                titel,
                ereignistyp="relativer_kurssturz",
                wert=_normierter_kurssturz_betrag(titel),
                schwelle=aktive_schwellen.get("relativer_kurssturz"),
                jetzt=jetzt,
            )
        )
        ereignisse.extend(
            _numerisches_ereignis(
                titel,
                ereignistyp="sentiment_kippen",
                wert=titel.sentiment_wert,
                schwelle=aktive_schwellen.get("sentiment_kippen"),
                jetzt=jetzt,
            )
        )
        ereignisse.extend(
            _numerisches_ereignis(
                titel,
                ereignistyp="momentum_verlust",
                wert=titel.momentum_wert,
                schwelle=aktive_schwellen.get("momentum_verlust"),
                jetzt=jetzt,
            )
        )
        ereignisse.extend(
            _numerisches_ereignis(
                titel,
                ereignistyp="on_chain_abfluss",
                wert=titel.on_chain_abfluss_wert,
                schwelle=aktive_schwellen.get("on_chain_abfluss"),
                jetzt=jetzt,
            )
        )
    return tuple(ereignisse)


def _news_ereignis(
    titel: TitelSignalRohdaten, *, keywords: Sequence[str], jetzt: datetime
) -> list[UeberwachungsEreignis]:
    relevante_news = filtere_relevante_news(titel.news, keywords=keywords)
    if not relevante_news:
        return []
    return [
        UeberwachungsEreignis(
            titel_id=titel.titel_id,
            ereignistyp="news_katalysator",
            rohwerte={
                "anzahl_treffer": str(len(relevante_news)),
                "texte": " | ".join(eintrag.text for eintrag in relevante_news),
            },
            zeitstempel=jetzt,
            quellen_id=relevante_news[0].quelle,
        )
    ]


def _normierter_kurssturz_betrag(titel: TitelSignalRohdaten) -> Decimal | None:
    """AC5: liefert den BETRAG der marktkontext-normierten Übertreibung
    (`abs(normierte_bewegung)`) — die Richtung (Sturz vs. Anstieg) ist für
    die Schwellenprüfung (AC6, "Überschreitet ... die Schwelle") nicht
    relevant, nur die Stärke der Abweichung vom Markt."""
    if titel.kursbewegung is None:
        return None
    normiert = normiere_kursbewegung(titel.kursbewegung, titel.marktbewegung)
    return abs(normiert.normierte_bewegung)


def _numerisches_ereignis(
    titel: TitelSignalRohdaten,
    *,
    ereignistyp: str,
    wert: Decimal | None,
    schwelle: Decimal | None,
    jetzt: datetime,
) -> list[UeberwachungsEreignis]:
    if wert is None or schwelle is None or wert <= schwelle:
        return []
    return [
        UeberwachungsEreignis(
            titel_id=titel.titel_id,
            ereignistyp=ereignistyp,  # type: ignore[arg-type]
            rohwerte={"wert": str(wert), "schwelle": str(schwelle)},
            zeitstempel=jetzt,
            quellen_id=titel.quelle,
        )
    ]


__all__ = ["erzeuge_ueberwachungsereignisse"]
