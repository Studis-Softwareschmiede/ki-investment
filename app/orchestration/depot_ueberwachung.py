"""Monitoring-Zyklus: Depot-Read, geteilte Abfrage & Toggle-/Frische-
Regeln (Modul 4, architecture.md §3, Story S-032, Spec
`docs/specs/depot-ueberwachung.md`).

Deckt Main-Success-Scenario Schritte 1-3 sowie A1 (AC8) und E1 (AC9):

- **AC1** — `fuehre_monitoring_zyklus_aus` liest je gehaltenem Titel
  Titel-Identität, Anlageklasse, Strategie und die beim Kauf fixierten
  Exit-Regeln über `app.domain.portfolio.portfolio_aggregate
  .ermittle_titel_strategie_exit_regeln` (bereits die für die
  Depot-Überwachung vorgesehene, per-Titel deduplizierte Sicht, S-036) —
  fehlt eines dieser Felder (`app.domain.depot_ueberwachung
  .vollstaendigkeit.ermittle_fehlende_felder`), wird der Titel als
  unvollständig protokolliert (`app.core.monitoring_audit_log`) und aus
  der weiteren Verarbeitung DIESES Zyklus ausgeschlossen — nicht
  stillschweigend, sondern sichtbar im zurückgelieferten Protokoll.

- **AC2 (DRY)** — für ALLE für diesen Zyklus zugelassenen Titel wird
  GENAU EINE gebündelte Anfrage (`SignalBuendelAnfrage` mit einem
  `TitelAnfrage`-Eintrag je Titel) an die geteilte Datenquellen-Abfrage
  (`app.orchestration.datasource_query.hole_signal_buendel`) gestellt —
  dieses Modul betreibt selbst KEINE eigene Preis-/Datenanbindung.

- **AC3** — je zugelassenem Titel werden die laut Anlageklasse
  überwachten Grössen bestimmt (`app.domain.depot_ueberwachung
  .ueberwachte_groessen.ermittle_ueberwachte_groessen`).

- **AC8, deckt A1** — `app.domain.depot_ueberwachung.toggle
  .ist_ueberwachung_erlaubt` lässt eine per Toggle deaktivierte
  Anlageklasse die Überwachung EINES BEREITS GEHALTENEN Titels nicht
  abschalten (`AssetClass.aktiv` wird nur informativ gelesen, nicht als
  Ausschlusskriterium verwendet).

- **AC9, deckt E1** — fehlt das Signal-Bündel eines zugelassenen Titels
  oder ist es älter als das konfigurierte Frische-Fenster
  (`app.domain.depot_ueberwachung.frische.ist_titel_bewertbar`,
  `Settings.depot_ueberwachung_frische_fenster_sekunden`), wird der Titel
  als nicht bewertbar protokolliert und NICHT in `ueberwachte_titel`
  aufgenommen — kein Ereignis wird aus fehlenden Daten fabriziert.

Ebenfalls nicht Teil dieser Story: das periodische/eventbasierte AUSLÖSEN
eines Zyklus (Scheduler-Integration, NFR "Prüffrequenz je Anlageklasse")
— analog `app.domain.kandidatensuche.kandidatensuche`-Docstring "das
tatsächliche Auslösen ... ist Sache der Folge-Stories bzw. der
Scheduler-Integration".

**Story S-033 (AC4-AC7)** ergänzt Main-Success-Scenario Schritte 4-6:

- `werte_monitoring_ereignisse_aus` filtert eingehende News gegen den
  Keyword-/Ereignis-Filter (AC4, `app.domain.depot_ueberwachung
  .ereignis_filter`), normiert Kursbewegungen gegen den Marktkontext
  (AC5, `.marktkontext`), erzeugt bei Schwellenüberschreitung
  Überwachungs-Ereignisse (AC6, `.ereignis_erzeugung` — kein eigener
  Kauf-/Verkaufs-Entscheid) und aktualisiert die Alert-Fatigue-
  Tageskennzahl (AC7, `app.core.monitoring_kennzahlen`).
- Input: `app.contracts.depot_ueberwachung.TitelSignalRohdaten` je Titel
  — ein **Cold-Start-Vertrag** (siehe dortiger Docstring): es existiert
  noch kein News-Text-Adapter/Markt-Referenz-Adapter, der ihn befüllt
  (analog `ExitRegelnBestand`, AC1 oben). Diese Funktion ist unabhängig
  davon bereits vollständig korrekt und getestet; sie ist bewusst NICHT
  an `fuehre_monitoring_zyklus_aus` verdrahtet (dessen
  `UeberwachterTitel.signal_buendel` liefert je Quelle nur einen
  aggregierten Zahlenwert, keine je Ereignistyp getaggten Rohsignale oder
  News-Freitext — die Ableitung dieser Rohsignale aus den vorhandenen
  Gold-Daten ist eine eigene, in dieser Story nicht spezifizierte
  Quant-Entscheidung, kein Bestandteil von AC4-AC7).
- Output: `MonitoringEreignisAuswertung` — die erzeugten
  `UeberwachungsEreignis`-Objekte (AC6) plus die aktualisierte
  `MonitoringTagesKennzahl` (AC7). Die tatsächliche "Weitergabe" an die
  Analyse bestehender Titel (`[[analyse-pipelines]]`, Sell-Pfad) ist noch
  nicht gebaut (S-034) — der Rückgabewert ist der vollständige,
  testbare Output dieser Story (analog `BuySignal`).

Analog `app.orchestration.datasource_query` (I/O-Layer, P2): SQLAlchemy-
Zugriff ist hier erlaubt, der reine Domain-Kern
(`app.domain.depot_ueberwachung.*`) bleibt I/O-frei (P1)."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.adapters.repositories.position_repository import SqlAlchemyPositionRepository
from app.config import get_settings
from app.contracts.dateneingang import SignalBuendel, SignalBuendelAnfrage, TitelAnfrage
from app.contracts.depot import Modus
from app.contracts.depot_ueberwachung import (
    MonitoringProtokollEintrag,
    MonitoringProtokollGrund,
    MonitoringTagesKennzahl,
    TitelSignalRohdaten,
    UeberwachungsEreignis,
)
from app.core.monitoring_audit_log import protokolliere
from app.core.monitoring_kennzahlen import berechne_tageskennzahl, registriere_ereignisse
from app.db.models import AssetClass
from app.domain.depot_ueberwachung.ereignis_erzeugung import erzeuge_ueberwachungsereignisse
from app.domain.depot_ueberwachung.frische import ist_titel_bewertbar
from app.domain.depot_ueberwachung.toggle import ist_ueberwachung_erlaubt
from app.domain.depot_ueberwachung.ueberwachte_groessen import ermittle_ueberwachte_groessen
from app.domain.depot_ueberwachung.vollstaendigkeit import ermittle_fehlende_felder
from app.domain.portfolio.portfolio_aggregate import (
    TitelStrategieExitRegeln,
    ermittle_titel_strategie_exit_regeln,
)
from app.orchestration.datasource_query import hole_signal_buendel


@dataclass(frozen=True)
class UeberwachterTitel:
    """Ein für diesen Zyklus vollständig gelesener (AC1), erlaubter (AC8)
    und bewertbarer (AC9) Titel inkl. seines Signal-Bündels (AC2) und der
    je Anlageklasse überwachten Grössen (AC3) — Grundlage für die
    Ereignis-Erkennung einer Folge-Story (AC4-AC7)."""

    titel_id: str
    anlageklasse: int
    strategie: str | None
    ueberwachte_groessen: tuple[str, ...]
    signal_buendel: SignalBuendel


@dataclass(frozen=True)
class MonitoringZyklusErgebnis:
    """Ergebnis eines Monitoring-Zyklus: die bewertbaren, überwachten
    Titel PLUS das Protokoll ALLER in diesem Zyklus übersprungenen Titel
    (`grund` = `unvollstaendig`/`nicht_bewertbar`) — "nicht stillschweigend
    übersprungen" (AC1/AC9)."""

    ueberwachte_titel: tuple[UeberwachterTitel, ...]
    protokoll: tuple[MonitoringProtokollEintrag, ...]


@dataclass(frozen=True)
class MonitoringEreignisAuswertung:
    """Ergebnis von `werte_monitoring_ereignisse_aus` (AC4-AC7): die in
    diesem Aufruf erzeugten Überwachungs-Ereignisse (AC6) plus die
    aktualisierte Alert-Fatigue-Tageskennzahl (AC7)."""

    ereignisse: tuple[UeberwachungsEreignis, ...]
    kennzahl: MonitoringTagesKennzahl


def fuehre_monitoring_zyklus_aus(
    session: Session, *, mode: Modus, jetzt: datetime | None = None
) -> MonitoringZyklusErgebnis:
    """Main-Success-Scenario Schritte 1-3 + A1 (AC8) + E1 (AC9), siehe
    Moduldocstring für die volle AC-Zuordnung. `mode` isoliert die
    gelesenen Positionen strikt (BR-113/BR-130, analog
    `app.domain.portfolio.portfolio_aggregate`) — echt/simuliert werden
    nie vermischt überwacht."""
    jetzt = jetzt or datetime.now(UTC)
    frische_fenster = timedelta(seconds=get_settings().depot_ueberwachung_frische_fenster_sekunden)
    protokoll: list[MonitoringProtokollEintrag] = []

    repository = SqlAlchemyPositionRepository(session)
    gehaltene_titel = ermittle_titel_strategie_exit_regeln(
        repository.alle_offenen_positionen(mode=mode)
    )

    vollstaendige_titel: list[TitelStrategieExitRegeln] = []
    for titel in gehaltene_titel:
        fehlende_felder = ermittle_fehlende_felder(titel)
        if fehlende_felder:
            _protokolliere(
                protokoll,
                titel_id=titel.titel_id,
                grund="unvollstaendig",
                detail="Fehlende Felder (AC1): " + ", ".join(fehlende_felder),
                jetzt=jetzt,
            )
            continue
        vollstaendige_titel.append(titel)

    erlaubte_titel = [
        titel
        for titel in vollstaendige_titel
        if ist_ueberwachung_erlaubt(aktiv=_ist_anlageklasse_aktiv(session, titel.anlageklasse))
    ]

    if not erlaubte_titel:
        return MonitoringZyklusErgebnis(ueberwachte_titel=(), protokoll=tuple(protokoll))

    anfrage = SignalBuendelAnfrage(
        titel_anfragen=[
            TitelAnfrage(titel=titel.titel_id, anlageklasse=titel.anlageklasse)
            for titel in erlaubte_titel
        ],
        konsumenten_kontext="bestehend",
    )
    signal_buendel_liste = hole_signal_buendel(session, anfrage)

    ueberwachte_titel: list[UeberwachterTitel] = []
    for titel, signal_buendel in zip(erlaubte_titel, signal_buendel_liste, strict=True):
        if not ist_titel_bewertbar(signal_buendel, jetzt=jetzt, frische_fenster=frische_fenster):
            _protokolliere(
                protokoll,
                titel_id=titel.titel_id,
                grund="nicht_bewertbar",
                detail=(
                    "Signal-Bündel fehlt oder ist älter als das Frische-Fenster "
                    f"({frische_fenster.total_seconds():.0f}s, AC9/E1)."
                ),
                jetzt=jetzt,
            )
            continue
        ueberwachte_titel.append(
            UeberwachterTitel(
                titel_id=titel.titel_id,
                anlageklasse=titel.anlageklasse,
                strategie=titel.strategie,
                ueberwachte_groessen=ermittle_ueberwachte_groessen(titel.anlageklasse),
                signal_buendel=signal_buendel,
            )
        )

    return MonitoringZyklusErgebnis(
        ueberwachte_titel=tuple(ueberwachte_titel), protokoll=tuple(protokoll)
    )


def _protokolliere(
    protokoll: list[MonitoringProtokollEintrag],
    *,
    titel_id: str,
    grund: MonitoringProtokollGrund,
    detail: str,
    jetzt: datetime,
) -> None:
    eintrag = MonitoringProtokollEintrag(
        zeitpunkt=jetzt, titel_id=titel_id, grund=grund, detail=detail
    )
    protokolliere(eintrag)
    protokoll.append(eintrag)


def _ist_anlageklasse_aktiv(session: Session, anlageklasse: int) -> bool:
    """Liest den reinen Toggle-Zustand (`AssetClass.aktiv`, S-003/AC12)
    einer Anlageklasse (analog `app.scheduler.scheduler
    ._hat_aktive_anlageklasse`) — NUR zur informativen Weitergabe an
    `ist_ueberwachung_erlaubt` (AC8), NICHT als Ausschlusskriterium für
    einen bereits gehaltenen Titel. Existiert (strukturell unerwartet)
    keine Stammdatenzeile für die Klasse, gilt sie konservativ als
    inaktiv (kein stillschweigender Normalbetriebs-Default) — ändert AC8
    ohnehin nichts, da die Überwachung eines gehaltenen Titels davon
    unabhängig bleibt."""
    aktiv = session.scalar(select(AssetClass.aktiv).where(AssetClass.id == anlageklasse))
    return bool(aktiv)


def werte_monitoring_ereignisse_aus(
    rohdaten: Sequence[TitelSignalRohdaten], *, jetzt: datetime | None = None
) -> MonitoringEreignisAuswertung:
    """Main-Success-Scenario Schritte 4-6 (AC4-AC7), siehe Moduldocstring
    für die volle AC-Zuordnung. Filtert News (AC4), normiert
    Kursbewegungen gegen den Marktkontext (AC5), erzeugt Überwachungs-
    Ereignisse bei Schwellenüberschreitung (AC6, kein eigener Kauf-/
    Verkaufs-Entscheid) und aktualisiert die Alert-Fatigue-Tageskennzahl
    (AC7). `rohdaten` ist der Cold-Start-Input, siehe Moduldocstring."""
    jetzt = jetzt or datetime.now(UTC)
    settings = get_settings()
    ereignisse = erzeuge_ueberwachungsereignisse(
        rohdaten,
        schwellen=settings.depot_ueberwachung_ereignis_schwellen,
        keywords=settings.depot_ueberwachung_ereignis_keywords,
        jetzt=jetzt,
    )
    registriere_ereignisse(len(ereignisse), zeitpunkt=jetzt)
    kennzahl = berechne_tageskennzahl(tag=jetzt.date())
    return MonitoringEreignisAuswertung(ereignisse=ereignisse, kennzahl=kennzahl)


__all__ = [
    "MonitoringEreignisAuswertung",
    "MonitoringZyklusErgebnis",
    "UeberwachterTitel",
    "fuehre_monitoring_zyklus_aus",
    "werte_monitoring_ereignisse_aus",
]
