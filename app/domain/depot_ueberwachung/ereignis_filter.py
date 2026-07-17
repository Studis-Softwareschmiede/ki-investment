"""Keyword-/Ereignis-Filter für eingehende News (Story S-033, Spec
`docs/specs/depot-ueberwachung.md` AC4, Main-Success-Scenario Schritt 4:
"filtert die eingehenden News/Ereignisse gegen den Keyword-/Ereignis-
Filter").

Reiner Domain-Kern (architecture.md §4 P1/P3): keine I/O. Operiert auf
`app.contracts.depot_ueberwachung.RohNewsEreignis` — Cold-Start-Vertrag
(siehe dortiger Docstring): es existiert noch kein News-Text-Adapter, der
diesen Vertrag befüllt; diese Funktion ist unabhängig davon vollständig
korrekt und getestet.

`filtere_relevante_news` ist die EINE Stelle, die AC4 auswertet: nur News,
deren Text (case-insensitiv, Teilstring) mindestens eines der
konfigurierten Stichworte enthält, gelten als "material relevant" und
werden durchgelassen; Duplikate (identischer Titel + normierter Text)
werden entdoppelt (erstes Vorkommen gewinnt, Reihenfolge bleibt stabil)."""

from __future__ import annotations

from collections.abc import Sequence

from app.contracts.depot_ueberwachung import DEFAULT_EREIGNIS_KEYWORDS, RohNewsEreignis


def filtere_relevante_news(
    news: Sequence[RohNewsEreignis], *, keywords: Sequence[str] = DEFAULT_EREIGNIS_KEYWORDS
) -> tuple[RohNewsEreignis, ...]:
    """AC4: liefert nur die Einträge aus `news`, deren Text mindestens
    eines der `keywords` (case-insensitiv, Teilstring) enthält —
    entdoppelt nach `(titel_id, normierter Text)`, erstes Vorkommen behält
    seine Position (stabile Reihenfolge)."""
    keywords_normiert = [keyword.casefold() for keyword in keywords if keyword.strip()]
    gesehen: set[tuple[str, str]] = set()
    ergebnis: list[RohNewsEreignis] = []
    for eintrag in news:
        text_normiert = eintrag.text.casefold()
        if not any(keyword in text_normiert for keyword in keywords_normiert):
            continue
        identitaet = (eintrag.titel_id, text_normiert.strip())
        if identitaet in gesehen:
            continue
        gesehen.add(identitaet)
        ergebnis.append(eintrag)
    return tuple(ergebnis)


__all__ = ["filtere_relevante_news"]
