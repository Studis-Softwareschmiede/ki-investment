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

Aus S-020 (AC10/AC11, `docs/specs/dateneingang.md`) kommen die
Scheduler-/Queue-Parameter hinzu (`app.scheduler.*`): Exponential-Backoff
(Basis-Wartezeit + maximale Versuche vor Dead-Letter-Queue, AC10) und
Token-Bucket je Quelle (Kapazität + Nachfüllrate, AC11). Beide Kriterien
nennen ihre Defaults explizit "provisorisch, konfigurierbar" — hier ohne
Codeänderung über `SCHEDULER_BACKOFF_BASIS_SEKUNDEN`/
`SCHEDULER_MAX_VERSUCHE`/`SCHEDULER_TOKEN_BUCKET_CAPACITY`/
`SCHEDULER_TOKEN_BUCKET_REFILL_PRO_SEKUNDE` überschreibbar (Muster von
`DRAWDOWN_*` folgend). Das Abrufintervall selbst (AC4) ist bereits über
die DB-Spalte `data_source.frequenz_sekunden` (S-006) ohne Codeänderung
konfigurierbar — dafür braucht es kein zusätzliches `Settings`-Feld.
Aus S-016 (AC5, BR-112) kommt `einstand_methode_default` hinzu: die
systemweite Default-Einstand-Methode (`gleitender_durchschnitt` | `fifo`),
die `app.domain.portfolio.position_booking.verbuche_fill` beim allerersten
Kauf eines Titels heranzieht (bereits offene Lots tragen ihre Methode
selbst, siehe `docs/data-model.md` §4 `position.einstand_methode`).
Default CH-Kontext (BR-112), ohne Codeänderung über
`EINSTAND_METHODE_DEFAULT` überschreibbar.
"""

from __future__ import annotations

from decimal import Decimal
from functools import lru_cache
from typing import Literal

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

    #: Exponential-Backoff-Basis (AC10, `app.scheduler.worker`): Wartezeit
    #: vor dem ERSTEN Retry-Versuch eines transienten Quellenfehlers
    #: (429/5xx/Timeout) in Sekunden; Folgeversuche verdoppeln sich je
    #: Versuch (`basis * 2**(versuch-1)`). Provisorischer Default 1.0s,
    #: ohne Codeänderung über `SCHEDULER_BACKOFF_BASIS_SEKUNDEN`
    #: überschreibbar.
    scheduler_backoff_basis_sekunden: float = Field(default=1.0, gt=0)

    #: Maximale Anzahl Verarbeitungsversuche (AC10) — nach Erschöpfung
    #: wandert das Arbeitselement in die Dead-Letter-Queue. Provisorischer
    #: Default 5, ohne Codeänderung über `SCHEDULER_MAX_VERSUCHE`
    #: überschreibbar.
    scheduler_max_versuche: int = Field(default=5, ge=1)

    #: Token-Bucket-Kapazität je Quelle (AC11) — maximale Anzahl sofort
    #: verfügbarer Abruf-„Tokens" (Burst), bevor ein Worker warten muss.
    #: Provisorischer Default 5, ohne Codeänderung über
    #: `SCHEDULER_TOKEN_BUCKET_CAPACITY` überschreibbar.
    scheduler_token_bucket_capacity: int = Field(default=5, ge=1)

    #: Token-Bucket-Nachfüllrate je Quelle (AC11), Tokens pro Sekunde.
    #: Provisorischer Default 1.0 (ein Abruf/Sekunde im Dauerbetrieb je
    #: Quelle), ohne Codeänderung über
    #: `SCHEDULER_TOKEN_BUCKET_REFILL_PRO_SEKUNDE` überschreibbar.
    scheduler_token_bucket_refill_pro_sekunde: float = Field(default=1.0, gt=0)
    #: Default-Einstand-Methode (AC5, BR-112) für den allerersten Kauf
    #: eines Titels — CH-Kontext, provisorisch. Ohne Codeänderung über
    #: `EINSTAND_METHODE_DEFAULT` auf `"fifo"` umstellbar.
    einstand_methode_default: Literal["gleitender_durchschnitt", "fifo"] = Field(
        default="gleitender_durchschnitt"
    )


@lru_cache
def get_settings() -> Settings:
    """Settings-Singleton (fastapi/A06) — Zugriff über diese Factory statt
    globaler Instanziierung, damit Tests sie via
    `get_settings.cache_clear()` (nach Env-Änderung) neu laden können."""
    return Settings()
