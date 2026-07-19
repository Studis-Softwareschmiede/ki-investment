"""Demo-Gate-Ampel (Story S-070, `docs/specs/frontend-cockpit.md` AC22):
`rule_hypothesis`/`trial_registry`/`gate_result` (Lernschleife, S-058/
S-059/S-062).

Schreibt ausschliesslich über die bestehenden Store-Funktionen
`app.db.rule_hypothesis.speichere_hypothese`,
`app.db.trial_registry.registriere_trial`,
`app.db.gate_result.registriere_gate_ergebnis` — die Ampel selbst leitet
der bestehende, reine Domain-Kern `app.domain.lernschleife.gate
.leite_ampel_ab` ab (kein DB-Zugriff, P1); dieses Modul erfindet keine
eigene Ampel-Logik. Kein Order-/Sizing-/Risiko-Bezug (Lernschleife ist ein
eigenständiges Modul, nicht Teil des Order-Pfads, siehe `tests/
architecture/test_order_pfad_invariante.py`-Glob-Katalog).

**Idempotent:** `rule_hypothesis.id` ist deterministisch
(`app.demo._namespace.demo_id`) — existiert die Demo-Hypothese bereits,
werden weder ein weiterer Trial noch ein weiteres Gate-Ergebnis angelegt
(`registriere_trial`/`registriere_gate_ergebnis` vergeben selbst
zufällige IDs und wären bei einem zweiten Aufruf NICHT idempotent — die
Existenzprüfung der Hypothese davor schützt vor dem Duplikat)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from sqlalchemy.orm import Session

from app.contracts.lernschleife import StufeAReport, StufeBReport
from app.contracts.research import Evidenzprotokoll, Hypothese
from app.db.gate_result import registriere_gate_ergebnis
from app.db.models import RuleHypothesis
from app.db.rule_hypothesis import speichere_hypothese
from app.db.trial_registry import registriere_trial
from app.demo._namespace import demo_id
from app.domain.lernschleife.gate import leite_ampel_ab

_DEMO_HYPOTHESE_ID = demo_id("demo-hypothese-krypto-momentum")


def seed_gate_ampel(session: Session) -> None:
    """AC22: eine Gate-Ampel — eine Hypothese, EIN Trial, EIN
    Gate-Ergebnis (Stufe A + Stufe B, Ampel "gruen")."""
    if session.get(RuleHypothesis, _DEMO_HYPOTHESE_ID) is not None:
        return

    hypothese = Hypothese(
        hypothese_id=_DEMO_HYPOTHESE_ID,
        beschreibung=(
            "Kryptowährungen zeigen nach starkem Whale-Alert-Zufluss ein "
            "kurzfristiges Momentum-Muster."
        ),
        marktlogik=(
            "Grosse On-Chain-Zuflüsse signalisieren institutionelles Interesse, "
            "das sich häufig in nachlaufender Kursbewegung niederschlägt."
        ),
        evidenz=Evidenzprotokoll(
            anzahl_faelle=42,
            zeitraum_von=datetime(2025, 1, 1, tzinfo=UTC),
            zeitraum_bis=datetime(2026, 6, 30, tzinfo=UTC),
            signalquelle="Whale Alert Blockchain",
            anlageklasse=7,
        ),
    )
    speichere_hypothese(
        session,
        hypothese=hypothese,
        params={"schwelle_chf": 1000000, "fenster_stunden": 24},
        free_param_count=2,
    )

    trial = registriere_trial(
        session,
        hypothesis_id=_DEMO_HYPOTHESE_ID,
        variant_hash="demo-seed-variant-001",
        params={"schwelle_chf": 1000000, "fenster_stunden": 24},
        getestet_am=datetime(2026, 7, 1, tzinfo=UTC),
    )

    stufe_a = StufeAReport(
        hypothesis_id=_DEMO_HYPOTHESE_ID,
        n_trades=42,
        embargo_tage=5,
        walk_forward_effizienz=Decimal("0.65"),
        dsr=Decimal("1.20"),
        ergebnis="bestanden",
        begruendung="Walk-Forward-Split bestanden, DSR über Schwelle.",
    )
    stufe_b = StufeBReport(
        hypothesis_id=_DEMO_HYPOTHESE_ID,
        n_trades=42,
        psr=Decimal("0.75"),
        benchmark_sharpe=Decimal("0"),
        psr_schwelle=Decimal("0.60"),
        psr_bestanden=True,
        mintrl_restlaufzeit=timedelta(days=30),
        begruendung="PSR über Schwelle im Paper-Betrieb.",
    )
    ampel = leite_ampel_ab(stufe_a, stufe_b)
    assert ampel is not None  # pragma: no cover — Stufe A "bestanden" liefert nie None

    registriere_gate_ergebnis(
        session,
        trial_id=trial.id,
        ampel=ampel,
        stufe_a_report=stufe_a,
        stufe_b_report=stufe_b,
    )
