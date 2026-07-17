"""Rule-Hypothesis-Store — Persistenz bereits AC1/AC2-geprüfter Hypothesen
aus Research (Story S-058, Spec `docs/specs/lernschleife.md` AC1/AC2, →
`docs/data-model.md` §6 `rule_hypothesis`).

AC1 ("Research ... übergibt sie an das Validierungs-Gate"): dieses Modul
bietet ausschliesslich `speichere_hypothese()` (Insert) — die AC1/AC2-
Konformität selbst (Mindest-Evidenz-Protokoll, Marktlogik-Filter) ist
bereits durch `app.contracts.research.Hypothese`/`Evidenzprotokoll`
(Pydantic-Vertrag) und `app.domain.research.hypothesen_erzeugung.
erzeuge_hypothesen` sichergestellt, BEVOR eine Hypothese hier ankommt —
`speichere_hypothese()` selbst nimmt keine fachliche Prüfung mehr vor
(reiner Insert, DB-CHECK/NOT-NULL als zweite Sicherungsebene, → BR-136)."""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from app.contracts.research import Hypothese
from app.db.models import RuleHypothesis


def speichere_hypothese(
    session: Session,
    *,
    hypothese: Hypothese,
    params: dict[str, Any],
    free_param_count: int,
) -> RuleHypothesis:
    """Persistiert eine bereits AC1/AC2-geprüfte `Hypothese` als
    `rule_hypothesis`-Zeile (Main Success Scenario Schritt 2: "übergibt
    sie an das Validierungs-Gate"). `params`/`free_param_count` sind die
    Regelparameter-Kandidaten der Hypothese (data-model.md §6, Basis für
    die spätere Trial-Registry-Variantenbildung/Overfit-Sanity, Folge-
    Story) — beide werden vom Aufrufer explizit übergeben, diese Funktion
    leitet sie nicht selbst her."""
    eintrag = RuleHypothesis(
        id=hypothese.hypothese_id,
        beschreibung=hypothese.beschreibung,
        marktlogik=hypothese.marktlogik,
        anzahl_faelle=hypothese.evidenz.anzahl_faelle,
        zeitraum_von=hypothese.evidenz.zeitraum_von,
        zeitraum_bis=hypothese.evidenz.zeitraum_bis,
        signalquelle=hypothese.evidenz.signalquelle,
        asset_class_id=hypothese.evidenz.anlageklasse,
        params=params,
        free_param_count=free_param_count,
    )
    session.add(eintrag)
    session.commit()
    return eintrag


__all__ = ["speichere_hypothese"]
