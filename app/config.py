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
Aus S-017 (AC11, `docs/specs/ausfuehrung-paper.md`) kommt
`erwartete_slippage_pct_default` hinzu: der provisorische, konfigurierbare
Prozentsatz, den `app.db.trading_platform.berechne_erwartete_kosten()` als
geschätzte Slippage in die Pre-Trade-Kostenkalkulation für die (künftigen)
Sizing-Module einrechnet. Weder Konzept noch Spec nennen einen konkreten
Wert (das eigentliche Paper-Slippage-/Spread-Modell aus AC9 ist eine eigene
Folge-Story, S-049, und modelliert die tatsächliche Fill-Slippage, nicht die
Pre-Trade-Schätzung dieser Story) — provisorisch gewählt: **5 Basispunkte
(0.05 %)**, ohne Codeänderung über `ERWARTETE_SLIPPAGE_PCT_DEFAULT`
überschreibbar (Muster von `HALLUZINATIONS_KPI_SCHWELLWERT` folgend).

Aus S-032 (AC9, `docs/specs/depot-ueberwachung.md`) kommt
`depot_ueberwachung_frische_fenster_sekunden` hinzu: das Frische-Fenster,
gegen das `app.domain.depot_ueberwachung.frische.ist_titel_bewertbar` das
jüngste Signal eines Signal-Bündels prüft — überschreitet dessen Alter
diesen Wert, gilt der Titel als „nicht bewertbar" (kein Ereignis wird aus
veralteten Daten fabriziert, deckt E1). Die Spec lässt den konkreten Wert
explizit offen ("Frische-Fenster" nur als konfigurierbarer Parameter
benannt) — provisorisch gewählt: **24 Stunden (86400s)**, ohne
Codeänderung über `DEPOT_UEBERWACHUNG_FRISCHE_FENSTER_SEKUNDEN`
überschreibbar (Muster von `HALLUZINATIONS_KPI_SCHWELLWERT` folgend).

Aus S-029 (AC6/AC7/AC10, `docs/specs/kandidatensuche.md`) kommen die
Kandidatensuche-Querschnitt-Filter-Schwellen +
Suchprofil-Konfig-Overrides hinzu (`app.domain.kandidatensuche.*`):
`kandidatensuche_liquiditaets_mindestschwelle` +
`kandidatensuche_volatilitaets_fenster_min`/`_max` (AC6, "auf jeden
Kandidaten angewandt" — Werte beziehen sich auf die bereits von
`app.orchestration.datasource_query` gelieferten `SignalBuendel.liquiditaet`
/`volatilitaet`-Proxys). Beide Schwellen sind laut Spec explizit
"provisorische Defaults, noch nicht kalibriert" — hier bewusst WEIT
gefasst gewählt (Liquidität ≥ 1 meldende Quelle, Volatilitäts-Fenster
[0, 1'000'000]), damit der uncalibrierte Default keinen Kandidaten
funktional ausschliesst ("Betrieb nur im Simulationsmodus sinnvoll", AC10)
— ohne Codeänderung über `KANDIDATENSUCHE_LIQUIDITAETS_MINDESTSCHWELLE`/
`KANDIDATENSUCHE_VOLATILITAETS_FENSTER_MIN`/`_MAX` überschreibbar.
`kandidatensuche_profil_overrides` (AC7 `modus`, AC10 `schwellen`) erlaubt
je Anlageklasse einen Konfig-Override eines registrierten `Suchprofil`
(`app.domain.kandidatensuche.suchprofil.wende_override_an`) über die
Umgebungsvariable `KANDIDATENSUCHE_PROFIL_OVERRIDES` (JSON-Mapping
Anlageklasse (als String-Key) → `{"modus": ..., "schwellen": {...}}`,
Muster von `TOLERANZ_CONFIG` folgend, hier aber pro Klasse gemerged statt
vollständig ersetzt, siehe `SuchprofilOverride`-Docstring).
"""

from __future__ import annotations

from decimal import Decimal
from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.contracts.kandidatensuche import (
    QuerschnittFilter,
    SuchprofilOverrides,
    VolatilitaetsFenster,
)
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
    #: Geschätzte Slippage (AC11, Pre-Trade-Kalkulation): Prozent-Zahl (z.B.
    #: `0.05` = 0.05 %, analog `platform_asset_class.courtage_pct`/
    #: `typ_spread_pct` in data-model.md — NICHT als Anteil 0-1 zu lesen)
    #: des Order-Werts, den
    #: `app.db.trading_platform.berechne_erwartete_kosten()` als geschätzte
    #: Slippage in die erwarteten Kosten einrechnet — bewusst kein
    #: Fill-Modell (das ist AC9/S-049, eigene Folge-Story). Provisorischer
    #: Default 0.05 % (5 Basispunkte), ohne Codeänderung über
    #: `ERWARTETE_SLIPPAGE_PCT_DEFAULT` überschreibbar.
    erwartete_slippage_pct_default: float = Field(default=0.05, ge=0)

    #: Querschnitt-Filter-Liquiditätsmindestschwelle (AC6, S-029) — bewusst
    #: weit gefasster, unkalibrierter Default (siehe Modul-Docstring), ohne
    #: Codeänderung über `KANDIDATENSUCHE_LIQUIDITAETS_MINDESTSCHWELLE`
    #: überschreibbar.
    kandidatensuche_liquiditaets_mindestschwelle: Decimal = Field(default=Decimal("1"))

    #: Querschnitt-Filter-Volatilitäts-Fenster Untergrenze (AC6, S-029),
    #: ohne Codeänderung über `KANDIDATENSUCHE_VOLATILITAETS_FENSTER_MIN`
    #: überschreibbar.
    kandidatensuche_volatilitaets_fenster_min: Decimal = Field(default=Decimal("0"))

    #: Querschnitt-Filter-Volatilitäts-Fenster Obergrenze (AC6, S-029),
    #: ohne Codeänderung über `KANDIDATENSUCHE_VOLATILITAETS_FENSTER_MAX`
    #: überschreibbar.
    kandidatensuche_volatilitaets_fenster_max: Decimal = Field(default=Decimal("1000000"))

    #: Suchprofil-Konfig-Overrides je Anlageklasse (AC7 `modus`, AC10
    #: `schwellen`, S-029) — ohne Codeänderung über
    #: `KANDIDATENSUCHE_PROFIL_OVERRIDES` überschreibbar (Default: kein
    #: Override, jedes registrierte Profil behält seinen Default-Wert).
    kandidatensuche_profil_overrides: SuchprofilOverrides = Field(default_factory=dict)

    #: Depot-Überwachung Frische-Fenster (AC9, S-032), in Sekunden —
    #: provisorischer Default 24h, ohne Codeänderung über
    #: `DEPOT_UEBERWACHUNG_FRISCHE_FENSTER_SEKUNDEN` überschreibbar (siehe
    #: Modul-Docstring).
    depot_ueberwachung_frische_fenster_sekunden: int = Field(default=86400, gt=0)


@lru_cache
def get_settings() -> Settings:
    """Settings-Singleton (fastapi/A06) — Zugriff über diese Factory statt
    globaler Instanziierung, damit Tests sie via
    `get_settings.cache_clear()` (nach Env-Änderung) neu laden können."""
    return Settings()


def lade_querschnitt_filter(settings: Settings | None = None) -> QuerschnittFilter:
    """AC6/AC10: baut den Querschnitt-Filter aus den konfigurierten (ohne
    Codeänderung überschreibbaren) `Settings`-Schwellen. `settings=None`
    liest den `get_settings()`-Singleton."""
    settings = settings or get_settings()
    return QuerschnittFilter(
        liquiditaets_mindestschwelle=settings.kandidatensuche_liquiditaets_mindestschwelle,
        volatilitaets_fenster=VolatilitaetsFenster(
            min=settings.kandidatensuche_volatilitaets_fenster_min,
            max=settings.kandidatensuche_volatilitaets_fenster_max,
        ),
    )
