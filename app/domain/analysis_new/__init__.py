"""Analyse neue Titel — Buy-Pfad (architecture.md §4 `domain/analysis_new/`,
Modul 7, C-011, Spec `docs/specs/analyse-pipelines.md`).

Verdrahtet die Score-Engine (`app.domain.scoring.score_engine`, S-010) mit
der No-Evidence-No-Trade-Prüfung (`app.domain.no_evidence_no_trade`, S-014)
zu einem deterministischen Buy-Pfad (S-028, AC1–AC4): `buy_pfad
.bewerte_kandidat` nimmt eine bereits über das LLM-Grounding-Gate geerdete
Analyse (`app.contracts.llm_grounding.AnalyseOutput`) entgegen und liefert
entweder ein `app.contracts.analyse_pipelines.BuySignal` (Gesamtscore ≥ 8
nach Risiko-Sanity-Cap) oder `None`.

Reiner Domain-Kern (architecture.md §4 P1/P3): keine I/O, kein LLM-Aufruf,
kein FastAPI, kein SQLAlchemy — die Grounding-Gate-Prüfung (Schema,
Input-Bindung, Cross-Check) läuft VOR diesem Modul im Adapter-Layer
(`app.adapters.llm`, ADR-003); dieses Paket konsumiert ausschließlich die
bereits validierten Verträge (`app/contracts/**`).

Der Sell-Pfad (Modul 8, `domain/analysis_existing/`, spätere Story S-034)
ist bewusst ein eigenständiges Paket — dieser Buy-Pfad kennt keinen
Sell-Signal-Typ und erzeugt strukturell nie eines (AC2).
"""

from __future__ import annotations
