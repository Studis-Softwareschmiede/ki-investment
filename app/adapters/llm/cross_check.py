"""Deterministischer Zahlen-Cross-Check (AC4, AC5 — Spec
`docs/specs/llm-grounding.md`, C-008 Sicherung 3, BR-004).

Sitzt architektonisch NACH dem Grounding-Gate (S-012,
`app.adapters.llm.grounding.pruefe_grounding`) im selben Adapter-Paket
(`adapters/llm`, ADR-003 "LLM-Adapter hinter dem Grounding-Gate") —
vergleicht jede referenzierte Zahl eines bereits schema-validierten,
input-gebundenen Outputs **ohne LLM-Beteiligung** gegen ihre
Originalquelle. Überschreitet die gemessene Abweichung die für den
Kennzahl-Typ konfigurierte Toleranz (AC5, absolut oder relativ), gilt die
Analyse als `verworfen` und der Vorfall wird protokolliert (AC10, deckt
E2).

Edge-Cases (Spec "Edge-Cases & Fehlerverhalten"):
- Originalquelle für einen Fakt nicht verfügbar → konservativ verwerfen
  (`quelle_nicht_verfuegbar`). Das gilt auch, wenn eine `quellen_id`
  zwar bekannt ist, aber für den konkret referenzierten Kennzahl-Typ des
  Fakts keine passende Originalquelle vorliegt (z.B. ein Filing mit
  mehreren Kennzahlen unter derselben `quellen_id`, aber nicht allen
  Kennzahl-Typen) — Review-Fix Iteration 2: `originalquellen` ist daher
  nach `(quellen_id, kennzahl_typ)` indiziert, nicht nur `quellen_id`.
- Toleranz für einen Kennzahl-Typ weder in `toleranz_config` noch in den
  Defaults (`app.config.DEFAULT_TOLERANZEN`) konfiguriert → verwerfen
  statt durchlassen (`toleranz_nicht_konfiguriert`).

NICHT Teil dieser Story: Halluzinations-KPI-Berechnung (AC8/AC9, spätere
Story) — das Cross-Check-Ergebnis liefert dafür lediglich die
strukturierte Grundlage.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from app.config import get_settings
from app.contracts.llm_grounding import (
    Abweichung,
    AnalyseFakt,
    CrossCheckErgebnis,
    Originalquelle,
    ProtokollEintrag,
    ProtokollGrund,
    ToleranzKonfig,
)
from app.core.audit_log import protokolliere


def _berechne_abweichung(
    wert_output: Decimal, wert_quelle: Decimal, toleranz: ToleranzKonfig
) -> Decimal:
    """Berechnet die Abweichung nach dem konfigurierten Toleranz-Typ (AC5):
    `absolut` = reine Differenz, `relativ` = Differenz als Bruchteil des
    Quellwerts. Ein Quellwert von exakt 0 fällt für `relativ` auf die
    absolute Differenz zurück (Division durch 0 vermeiden). Rechnet
    durchgehend in `Decimal` (architecture.md P7) — keine
    Float-Rundungsdrift im Toleranzvergleich."""
    differenz = abs(wert_output - wert_quelle)
    if toleranz.typ == "absolut" or wert_quelle == 0:
        return differenz
    return differenz / abs(wert_quelle)


def _protokolliere_ablehnung(
    *, grund: ProtokollGrund, kennzahl_typ: str | None, quellen_id: str | None, detail: str
) -> ProtokollEintrag:
    eintrag = ProtokollEintrag(
        zeitpunkt=datetime.now(UTC),
        grund=grund,
        kennzahl_typ=kennzahl_typ,
        quellen_id=quellen_id,
        detail=detail,
    )
    protokolliere(eintrag)
    return eintrag


def pruefe_cross_check(
    output_fakten: tuple[AnalyseFakt, ...],
    originalquellen: dict[tuple[str, str], Originalquelle],
    toleranz_config: dict[str, ToleranzKonfig] | None = None,
) -> CrossCheckErgebnis:
    """Vergleicht jede referenzierte Zahl deterministisch (kein LLM, keine
    Systemzeit-Abhängigkeit im Vergleich selbst) gegen ihre Originalquelle
    (AC4). `originalquellen` ist nach `(quellen_id, kennzahl_typ)`
    indiziert — NICHT nur `quellen_id` — damit eine `quellen_id` mit
    mehreren berichteten Kennzahlen (z.B. ein Filing mit KGV, Kurs,
    Marktkapitalisierung) nicht kollidiert bzw. gegen den falschen
    Originalwert prüft (Review-Fix Iteration 2). `toleranz_config`
    überschreibt je Kennzahl-Typ die provisorischen Defaults aus
    `app.config.DEFAULT_TOLERANZEN` (AC5); fehlt ein Eintrag dort UND in
    den Defaults, wird konservativ verworfen (Edge-Case "Toleranz nicht
    konfiguriert"). Bricht bei der ersten verwerfenden Abweichung/dem
    ersten Edge-Case ab."""
    effektive_toleranzen: dict[str, ToleranzKonfig] = dict(get_settings().toleranz_config)
    if toleranz_config:
        effektive_toleranzen.update(toleranz_config)

    abweichungen: list[Abweichung] = []

    for fakt in output_fakten:
        quelle = originalquellen.get((fakt.quellen_id, fakt.kennzahl_typ))
        if quelle is None:
            eintrag = _protokolliere_ablehnung(
                grund="quelle_nicht_verfuegbar",
                kennzahl_typ=fakt.kennzahl_typ,
                quellen_id=fakt.quellen_id,
                detail=(
                    f"Originalquelle {fakt.quellen_id} für Kennzahl "
                    f"{fakt.kennzahl_typ} nicht verfügbar — konservativ verworfen."
                ),
            )
            return CrossCheckErgebnis(
                status="verworfen",
                abweichungen=tuple(abweichungen),
                protokoll_eintrag=eintrag,
            )

        toleranz = effektive_toleranzen.get(fakt.kennzahl_typ)
        if toleranz is None:
            eintrag = _protokolliere_ablehnung(
                grund="toleranz_nicht_konfiguriert",
                kennzahl_typ=fakt.kennzahl_typ,
                quellen_id=fakt.quellen_id,
                detail=(
                    f"Keine Toleranz für Kennzahl-Typ {fakt.kennzahl_typ} "
                    "konfiguriert (auch kein Default) — verworfen statt durchgelassen."
                ),
            )
            return CrossCheckErgebnis(
                status="verworfen",
                abweichungen=tuple(abweichungen),
                protokoll_eintrag=eintrag,
            )

        abweichung_wert = _berechne_abweichung(fakt.wert, quelle.wert, toleranz)
        abweichungen.append(
            Abweichung(
                kennzahl_typ=fakt.kennzahl_typ,
                wert_output=fakt.wert,
                wert_quelle=quelle.wert,
                abweichung=abweichung_wert,
                toleranz=toleranz.schwelle,
            )
        )

        if abweichung_wert > toleranz.schwelle:
            eintrag = _protokolliere_ablehnung(
                grund="cross_check_abweichung",
                kennzahl_typ=fakt.kennzahl_typ,
                quellen_id=fakt.quellen_id,
                detail=(
                    f"{fakt.kennzahl_typ}: Output={fakt.wert}, Quelle={quelle.wert}, "
                    f"Abweichung={abweichung_wert:.6f} > Toleranz={toleranz.schwelle} "
                    f"({toleranz.typ})."
                ),
            )
            return CrossCheckErgebnis(
                status="verworfen",
                abweichungen=tuple(abweichungen),
                protokoll_eintrag=eintrag,
            )

    return CrossCheckErgebnis(status="geerdet", abweichungen=tuple(abweichungen))
