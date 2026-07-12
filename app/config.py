"""Anwendungsweite Konfiguration (architecture.md §4 `app/config.py`:
"Settings via pydantic-settings; lädt Feature-Toggles + Modus-Schalter",
fastapi/A06).

Für diese Story (S-013, AC5) trägt dieses Modul die konfigurierbaren
Toleranzschwellen des deterministischen Zahlen-Cross-Checks
(`app.adapters.llm.cross_check`) je Kennzahl-Typ — **ohne Codeänderung**
über die Umgebungsvariable `TOLERANZ_CONFIG` (JSON-codiertes Mapping
Kennzahl-Typ → `{typ, schwelle}`, pydantic-settings parst komplexe Felder
aus einem JSON-String) oder eine `.env`-Datei überschreibbar. Weitere
Feature-Toggles/Modus-Schalter (z.B. Order-Modus echt/simuliert) folgen in
späteren Stories und erweitern `Settings`, ohne bestehende Felder zu
berühren.

Aus S-027 (AC9, BR-006) kommt `halluzinations_kpi_schwellwert` hinzu: der
Schwellwert (Default 2 %), ab dessen STRIKTER Überschreitung
`app.core.hallucination_kpi.berechne_kpi` das LLM aus der Entscheidungskette
nimmt — ebenfalls ohne Codeänderung über die Umgebungsvariable
`HALLUZINATIONS_KPI_SCHWELLWERT` überschreibbar (Muster von `TOLERANZ_CONFIG`
folgend, hier aber ein einzelner Skalar statt eines Mappings).

Aus S-025 (AC2, AC5, `docs/specs/betriebssicherung.md`) kommen
`drawdown_alert_schwelle` + `drawdown_kill_schwelle` hinzu: die zwei
UNABHÄNGIG konfigurierbaren Drawdown-Schwellen, die
`app.core.drawdown_monitor.pruefe_drawdown()` gegen den laufend
aktualisierten Portfolio-Drawdown vergleicht. Die Spec lässt den konkreten
Default explizit offen ("konkreter Default provisorisch/offen — in der
Umsetzung festzulegen", AC2) — provisorisch gewählt: **Alert bei 10 %,
Kill bei 20 %** Rückgang vom laufenden Höchststand. Beide Werte sind ohne
Codeänderung über `DRAWDOWN_ALERT_SCHWELLE`/`DRAWDOWN_KILL_SCHWELLE`
überschreibbar (Muster von `HALLUZINATIONS_KPI_SCHWELLWERT` folgend).
"""

from __future__ import annotations

from decimal import Decimal
from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.contracts.llm_grounding import ToleranzKonfig

#: Provisorische Default-Toleranzen je Kennzahl-Typ (AC5 — "ihre konkrete
#: Festlegung ist offen/provisorisch"). Greifen nur für Kennzahl-Typen ohne
#: eigenen Eintrag in `TOLERANZ_CONFIG`/im Aufrufparameter
#: `toleranz_config` (Edge-Case "Toleranz nicht konfiguriert" — Default
#: statt Codeänderung).
DEFAULT_TOLERANZEN: dict[str, ToleranzKonfig] = {
    "kgv": ToleranzKonfig(kennzahl_typ="kgv", typ="relativ", schwelle=Decimal("0.02")),
    "kurs": ToleranzKonfig(kennzahl_typ="kurs", typ="relativ", schwelle=Decimal("0.01")),
    "marktkapitalisierung": ToleranzKonfig(
        kennzahl_typ="marktkapitalisierung", typ="relativ", schwelle=Decimal("0.02")
    ),
}


class Settings(BaseSettings):
    """Settings-Klasse (fastapi/A06) — Werte aus Env-Variablen/`.env`,
    NIE hartkodierte Secrets. `toleranz_config` ist bewusst kein Secret,
    sondern ein fachlicher Konfigurationsparameter (AC5)."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    #: Wird `TOLERANZ_CONFIG` gesetzt (Env-Variable, JSON-codiertes
    #: Mapping), ERSETZT sie das VOLLSTÄNDIGE `DEFAULT_TOLERANZEN`-Mapping
    #: — pydantic-settings merged komplexe Feldtypen NICHT mit dem
    #: `default_factory`-Wert. Ein Override, der nur einen Kennzahl-Typ
    #: enthält, lässt alle anderen Kennzahl-Typen ohne Toleranz zurück
    #: (→ Edge-Case "Toleranz nicht konfiguriert" in
    #: `app.adapters.llm.cross_check`, verwirft statt durchzulassen). Wer
    #: nur einen einzelnen Wert anpassen will, muss das gesamte Mapping
    #: (alle Kennzahl-Typen) in `TOLERANZ_CONFIG` mitliefern.
    toleranz_config: dict[str, ToleranzKonfig] = Field(
        default_factory=lambda: dict(DEFAULT_TOLERANZEN)
    )

    #: Schwellwert der Halluzinations-KPI (AC9, BR-006): übersteigt die aus
    #: dem Cross-Check gemessene Quote „Analysen mit Faktenabweichung"
    #: diesen Wert STRIKT (`>`, nicht `>=` — Edge-Case „genau am Schwellwert
    #: → kein Alarm"), nimmt `app.core.hallucination_kpi` das LLM aus der
    #: Entscheidungskette. Default 2 % (0.02), ohne Codeänderung über
    #: `HALLUZINATIONS_KPI_SCHWELLWERT` überschreibbar.
    halluzinations_kpi_schwellwert: float = Field(default=0.02, ge=0)

    #: Drawdown-Alert-Schwelle (AC5): überschreitet der relative Rückgang
    #: vom laufenden Höchststand (High-Water-Mark) diesen Wert STRIKT, gibt
    #: `app.core.drawdown_monitor.pruefe_drawdown()` einen `warn`-Alert
    #: aus. UNABHÄNGIG von `drawdown_kill_schwelle` konfigurierbar (AC5).
    #: Provisorischer Default 10 % (AC2 — konkreter Wert offen, s.
    #: Modul-Docstring), ohne Codeänderung über `DRAWDOWN_ALERT_SCHWELLE`
    #: überschreibbar.
    drawdown_alert_schwelle: float = Field(default=0.10, ge=0, le=1)

    #: Drawdown-Kill-Schwelle (AC2): überschreitet der relative Rückgang
    #: vom laufenden Höchststand diesen Wert STRIKT, löst
    #: `app.core.drawdown_monitor.pruefe_drawdown()` automatisch den
    #: bestehenden `app.core.kill_switch.ausloesen()` aus (Quelle
    #: `"drawdown"`). Provisorischer Default 20 % (s. Modul-Docstring),
    #: ohne Codeänderung über `DRAWDOWN_KILL_SCHWELLE` überschreibbar.
    drawdown_kill_schwelle: float = Field(default=0.20, ge=0, le=1)


@lru_cache
def get_settings() -> Settings:
    """Settings-Singleton (fastapi/A06) — Zugriff über diese Factory statt
    globaler Instanziierung, damit Tests sie via
    `get_settings.cache_clear()` (nach Env-Änderung) neu laden können."""
    return Settings()
