"""Je Anlageklasse überwachte Grössen (Story S-032, Spec
`docs/specs/depot-ueberwachung.md` AC3, Main-Success-Scenario Schritt 2:
"Es bestimmt anhand der Anlageklasse die relevanten Datenquellen und die
je Klasse überwachten Grössen (profilbasiert, kein Einheitsfilter).").

Reiner Domain-Kern (architecture.md §4 P1/P3): keine I/O, kein
SQLAlchemy. `ermittle_ueberwachte_groessen` ist die EINE Stelle, die
AC3 auswertet — jede Anlageklasse erhält mindestens die vier
Standard-Grössen (News-Katalysatoren, relativer Kurssturz,
Sentiment-Kippen, Momentum-Verlust); Anlageklasse 7 (Krypto) erhält
zusätzlich On-Chain-Abflüsse. "Nicht zur Klasse passende Grössen werden
nicht abgefragt" (AC3) — es existiert bewusst KEIN Einheitsfilter, der
allen Klassen dieselbe (grössere) Grössen-Menge zuweisen würde.

Die inhaltliche AUSWERTUNG dieser Grössen gegen Schwellen (Keyword-/
Ereignis-Filter AC4, Marktkontext-Normierung AC5, Ereignis-Erzeugung AC6,
Alert-Fatigue-Kennzahl AC7) ist NICHT Teil dieser Story — dieses Modul
liefert nur, WELCHE Grössen für eine Klasse relevant sind."""

from __future__ import annotations

#: Anlageklasse 7 = "Krypto" (verbindliche Nummerierung C-006,
#: `docs/specs/anlageklassen-config.md` AC1) — einzige Klasse mit
#: zusätzlicher On-Chain-Grösse (AC3).
KRYPTO_ANLAGEKLASSE = 7

#: Standard-Grössen, die für JEDE Anlageklasse überwacht werden (AC3
#: "mindestens News-Katalysatoren, relativer Kurssturz, Sentiment-Kippen
#: und Momentum-Verlust").
UEBERWACHTE_GROESSEN_STANDARD: tuple[str, ...] = (
    "news_katalysatoren",
    "relativer_kurssturz",
    "sentiment_kippen",
    "momentum_verlust",
)

#: Zusätzliche Grösse NUR für Anlageklasse 7/Krypto (AC3 "für Anlageklasse
#: 7 (Krypto) zusätzlich On-Chain-Abflüsse").
UEBERWACHTE_GROESSEN_KRYPTO_ZUSATZ: tuple[str, ...] = ("on_chain_abfluesse",)


def ermittle_ueberwachte_groessen(anlageklasse: int) -> tuple[str, ...]:
    """AC3: die für `anlageklasse` überwachten Grössen — die vier
    Standard-Grössen für jede Klasse, plus On-Chain-Abflüsse ausschliesslich
    für Anlageklasse 7 (Krypto). Keine andere Klasse erhält die
    Krypto-Zusatzgrösse (kein Einheitsfilter)."""
    if anlageklasse == KRYPTO_ANLAGEKLASSE:
        return UEBERWACHTE_GROESSEN_STANDARD + UEBERWACHTE_GROESSEN_KRYPTO_ZUSATZ
    return UEBERWACHTE_GROESSEN_STANDARD


__all__ = [
    "KRYPTO_ANLAGEKLASSE",
    "UEBERWACHTE_GROESSEN_KRYPTO_ZUSATZ",
    "UEBERWACHTE_GROESSEN_STANDARD",
    "ermittle_ueberwachte_groessen",
]
