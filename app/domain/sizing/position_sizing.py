"""Position-Sizing-Kern (Story S-039, Spec `docs/specs/sizing.md`
AC1/AC2/AC3/AC4/AC7).

Reiner Domain-Kern (architecture.md §4 P1/P3): keine I/O, kein LLM, keine
DB, keine Systemzeit-Abhängigkeit (architecture.md P3, "deterministischer
Order-Pfad"). Deckt:

- **AC1** — `berechne_kelly_fraktion`: Fractional-Kelly-Formel
  `f* = (b·p − q)/b` (`p` = Win-Wahrscheinlichkeit, `q = 1−p`, `b` =
  Gewinn/Verlust-Verhältnis). Ist `f*` ≤ 0, wird kein Trade erzeugt
  (`verworfen="kelly-negativ"`, deckt E1).
- **AC2** — `bestimme_konfigurierte_fraktion`: Standard-Fraktion ist
  Half-Kelly; für volatile Anlageklassen (Krypto, Anlageklasse 7, C-006)
  gilt Quarter-Kelly, das zugleich als Obergrenze der eingesetzten
  Fraktion wirkt. Beide Fraktionen sind konfigurierbar
  (`KellyFraktionsKonfiguration`).
- **AC3** — `berechne_positionsgroesse`: zusätzlich zur Kelly-Fraktion
  greift ein hartes Cap auf das Risiko je Trade (Default 1–2 % des
  Kapitals, konfigurierbar) — unabhängig davon, was Kelly vorschlägt,
  gewinnt die kleinere der beiden Grössen (`min(...)`). Das Cap gilt für
  BEIDE Zweige (Kelly und den Fixed-Fractional-Rückfall aus AC4) — ein
  "hartes" Cap, das laut Spec "unabhängig davon [gilt], was Kelly
  vorschlägt", schützt konsistenterweise auch den konservativeren
  Rückfallpfad.
- **AC4** — Kelly wird erst "scharf" angewendet, wenn
  `abgeschlossene_sim_trades` die konfigurierte Mindestzahl (Default 100,
  Spec-Bereich 50–100) erreicht; darunter greift die konservative
  Fixed-Fractional-Regel (deckt A2).
- **AC7** — Mikro-Betrachtung: diese Funktionen nehmen bewusst keine
  Portfolio-/Depot-Daten entgegen und führen keine Korrelations-/
  Klumpenrisiko-Prüfung durch — das macht das nachgelagerte
  Risikomanagement (`app.db.depotstrategie`, S-043, `[[risikomanagement]]`).

`trade_cap_pct` (AC3) ist ein reiner Funktionsparameter mit Default; ein
künftiger Orchestrierungs-Layer kann ihn z.B. aus
`app.db.depotstrategie.lade_aktive_depotstrategie().max_einzelposition_pct`
speisen, damit eine Einzelposition das dort konfigurierte
Depotstrategie-Cap nie überschreitet — diese Verdrahtung (DB-Zugriff) ist
bewusst NICHT Teil dieser reinen Kern-Story (P1/P3: kein DB-Zugriff in
`domain/`).

Weder `ordergroesse` (absolute Geldsumme) noch die Pre-Trade-Kosten-
kalkulation (AC5) oder die Mindest-Ordergrösse-Prüfung (AC6) sind Teil
dieser Story (siehe `app.contracts.sizing`-Moduldocstring) — dieses Modul
liefert ausschliesslich den Risiko-Anteil des Kapitals (`risiko_pct`).
"""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal

from app.contracts.sizing import KellyFraktionsKonfiguration, PositionSizingErgebnis

#: AC2: fest verdrahtete Obergrenze der für volatile Anlageklassen
#: eingesetzten Fraktion ("Quarter-Kelly wirkt zugleich als Obergrenze
#: der eingesetzten Fraktion") — ein niedrigerer `fraktion_volatil`-Wert
#: in `KellyFraktionsKonfiguration` ist zulässig, ein höherer wird hier
#: gekappt.
QUARTER_KELLY_OBERGRENZE = Decimal("0.25")

#: Rundungsraster für die Ausgabewerte dieses Moduls (Anteile 0–1, 6
#: Nachkommastellen) — kaufmännisch gerundet (`ROUND_HALF_UP`), analog zu
#: `app.domain.portfolio.position_booking._quantize_geld` (P7/ADR-010).
_ANTEIL_QUANTUM = Decimal("0.000001")


def _quantize_anteil(wert: Decimal) -> Decimal:
    return wert.quantize(_ANTEIL_QUANTUM, rounding=ROUND_HALF_UP)


def ist_volatile_anlageklasse(
    anlageklasse: int,
    konfiguration: KellyFraktionsKonfiguration | None = None,
) -> bool:
    """AC2/P6: `True`, wenn `anlageklasse` (Anlageklassen-ID, C-006) laut
    Konfiguration als volatil gilt (Default: Krypto = 7). Die Menge der
    volatilen Klassen kommt aus `konfiguration.volatile_anlageklassen_ids`
    (überschreibbare Konfiguration statt hartkodierter Code-Grenze im Kern —
    architecture.md §2 P6)."""
    aktive_konfiguration = konfiguration or KellyFraktionsKonfiguration()
    return anlageklasse in aktive_konfiguration.volatile_anlageklassen_ids


def berechne_kelly_fraktion(p: Decimal, b: Decimal) -> Decimal:
    """AC1: Fractional-Kelly-Formel `f* = (b·p − q)/b`, `q = 1−p`.

    Raises:
        ValueError: `p` liegt ausserhalb `[0, 1]` (keine gültige
            Wahrscheinlichkeit) oder `b` ist `<= 0` (kein gültiges
            Gewinn/Verlust-Verhältnis — Division durch 0 bzw. Vorzeichen-
            Umkehr der Formel wären sonst nicht definiert).
    """
    if not (Decimal(0) <= p <= Decimal(1)):
        raise ValueError(f"p muss in [0, 1] liegen, war {p!r}.")
    if b <= 0:
        raise ValueError(f"b (Gewinn/Verlust-Verhältnis) muss > 0 sein, war {b!r}.")

    q = Decimal(1) - p
    return (b * p - q) / b


def bestimme_konfigurierte_fraktion(
    anlageklasse: int,
    konfiguration: KellyFraktionsKonfiguration | None = None,
) -> Decimal:
    """AC2: Standard-Fraktion (Half-Kelly) für nicht-volatile
    Anlageklassen; für volatile Anlageklassen (Krypto) die konfigurierte
    `fraktion_volatil`, hart gedeckelt auf `QUARTER_KELLY_OBERGRENZE`
    ("Quarter-Kelly wirkt zugleich als Obergrenze der eingesetzten
    Fraktion")."""
    aktive_konfiguration = konfiguration or KellyFraktionsKonfiguration()
    if ist_volatile_anlageklasse(anlageklasse, aktive_konfiguration):
        return min(aktive_konfiguration.fraktion_volatil, QUARTER_KELLY_OBERGRENZE)
    return aktive_konfiguration.fraktion_standard


def berechne_positionsgroesse(
    *,
    titel_id: str,
    p: Decimal,
    b: Decimal,
    anlageklasse: int,
    abgeschlossene_sim_trades: int,
    konfiguration: KellyFraktionsKonfiguration | None = None,
) -> PositionSizingErgebnis:
    """Position-Sizing-Kern: verdrahtet AC1 (Kelly-Formel), AC2
    (Half-/Quarter-Kelly-Fraktion), AC3 (hartes Cap) und AC4
    (Scharfschaltung) zum `PositionSizingErgebnis`.

    - `abgeschlossene_sim_trades` < `konfiguration.kelly_min_trades`
      (AC4, Default 100): Kelly ist nicht scharf — es gilt die
      konservative `fixed_fractional_pct`-Regel (deckt A2), begrenzt
      durch das AC3-Cap.
    - Sonst (Kelly scharf): `f*` wird berechnet (AC1). Ist `f*` ≤ 0,
      entsteht kein Trade (`verworfen="kelly-negativ"`, `risiko_pct=0`,
      deckt E1). Sonst wird `f*` mit der AC2-Fraktion multipliziert und
      auf das AC3-Cap begrenzt (die kleinere der beiden Grössen
      gewinnt).

    AC7: nimmt bewusst keine Portfolio-/Depot-Daten entgegen — reine
    Mikro-Betrachtung des einzelnen Titels.
    """
    aktive_konfiguration = konfiguration or KellyFraktionsKonfiguration()
    kelly_scharf = abgeschlossene_sim_trades >= aktive_konfiguration.kelly_min_trades

    if not kelly_scharf:
        risiko_pct = min(
            aktive_konfiguration.fixed_fractional_pct, aktive_konfiguration.trade_cap_pct
        )
        return PositionSizingErgebnis(
            titel_id=titel_id,
            eingesetzte_kelly_fraktion=None,
            risiko_pct=_quantize_anteil(risiko_pct),
            kelly_scharf=False,
            verworfen=None,
        )

    kelly_fraktion = berechne_kelly_fraktion(p, b)  # AC1
    if kelly_fraktion <= 0:
        return PositionSizingErgebnis(
            titel_id=titel_id,
            eingesetzte_kelly_fraktion=_quantize_anteil(kelly_fraktion),
            risiko_pct=Decimal(0),
            kelly_scharf=True,
            verworfen="kelly-negativ",
        )

    konfigurierte_fraktion = bestimme_konfigurierte_fraktion(anlageklasse, aktive_konfiguration)
    eingesetzte_kelly_fraktion = kelly_fraktion * konfigurierte_fraktion  # AC2
    risiko_pct = min(eingesetzte_kelly_fraktion, aktive_konfiguration.trade_cap_pct)  # AC3

    return PositionSizingErgebnis(
        titel_id=titel_id,
        eingesetzte_kelly_fraktion=_quantize_anteil(eingesetzte_kelly_fraktion),
        risiko_pct=_quantize_anteil(risiko_pct),
        kelly_scharf=True,
        verworfen=None,
    )


__all__ = [
    "QUARTER_KELLY_OBERGRENZE",
    "berechne_kelly_fraktion",
    "berechne_positionsgroesse",
    "bestimme_konfigurierte_fraktion",
    "ist_volatile_anlageklasse",
]
