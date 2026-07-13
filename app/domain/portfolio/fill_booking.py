"""Fill-Buchungs-Gate (Modul 16 Depotmodul, Spec `docs/specs/depot.md`,
Story S-015, AC1 + AC10).

`pruefe_fill()` ist der **Buchungs-Eintrittspunkt**: er entscheidet, ob ein
Ausführungsergebnis (Fill) überhaupt gebucht werden darf — er bucht
**nichts** selbst (kein DB-Write). Zwei Prüfungen, eine gemeinsame
Ablehnung (AC10, deckt E1):

1. **Universelle Pflichtfelder + Kauf-Pflichtattribute (AC1/AC10).** Über
   `app.contracts.depot.FillInput` (inkl. `model_validator` für die
   Kauf-only-Felder Strategie/Zeithorizont/Exit-Regeln/These, AC1). Fehlt
   eines, verweigert pydantic die Instanziierung — hier abgefangen und in
   ein strukturiertes Ablehnungs-Ergebnis übersetzt (Muster identisch zu
   `app.adapters.sockets.base.SocketAdapter.fetch`).
2. **Keine resultierende negative Menge (AC10).** Die resultierende Menge
   (aktueller Bestand ± Fill-Menge, je nach Richtung) darf nicht negativ
   werden — sonst würde mehr verkauft, als gehalten wird. Der aktuelle
   Bestand kommt über den injizierten `PositionRepository`-Port (P1: der
   Domain-Kern greift nie direkt auf SQLAlchemy/DB zu).

Bei Erfolg (`status == "gebucht"`) liefert das Ergebnis nur das validierte
`FillInput` plus die berechnete `resultierende_menge` — die eigentliche
Positions-Fortschreibung (Ø-Einstand-Berechnung, Gebühren-Netting in die
Kostenbasis, Einstand-Methode gleitender Ø/FIFO) ist **NICHT** Teil dieser
Story (S-016, AC2/AC3/AC5); ebenso wenig die Transaktionshistorie/TCA
(S-035, AC4/AC7) oder die Portfolio-Aggregate (S-036, AC8/AC9).

DBA-Re-Review von S-016 (Iteration 3, Important — Mode-Isolation, BR-113/
BR-130) zieht denselben Fix hier nach: `repository.aktuelle_menge` wird mit
`mode=fill.mode` aufgerufen, damit der Bestandsvergleich (AC10) nur den
Bestand DESSELBEN Modus berücksichtigt — ein „echt"-Verkauf darf nicht
gegen einen „simuliert"-Bestand desselben Titels gedeckt erscheinen (und
umgekehrt).
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any

from pydantic import ValidationError

from app.contracts.depot import (
    FillAblehnungsgrund,
    FillErgebnis,
    FillInput,
    FillProtokollEintrag,
    Richtung,
)
from app.core.depot_audit_log import protokolliere
from app.domain.portfolio.ports import PositionRepository


def pruefe_fill(rohdaten: Mapping[str, Any], *, repository: PositionRepository) -> FillErgebnis:
    """Prüft ein Ausführungsergebnis (Fill) vor der Buchung (AC1, AC10,
    deckt E1). `rohdaten` ist bewusst ein loses Mapping (nicht bereits ein
    `FillInput`) — das Kauf-/Verkaufsmodul liefert das Ergebnis als
    Rohstruktur, deren Vollständigkeit/Konsistenz Depot selbst prüft, statt
    sie stillschweigend als bereits geprüft anzunehmen."""
    try:
        fill = FillInput(**rohdaten)
    except ValidationError as exc:
        eintrag = _protokolliere_ablehnung(
            grund="unvollstaendig",
            titel_id=_als_str(rohdaten.get("titel_id")),
            richtung=_als_richtung(rohdaten.get("richtung")),
            detail=(
                f"Fill nicht gebucht (AC1/AC10): fehlende oder ungültige Pflichtfelder — {exc}"
            ),
        )
        return FillErgebnis(status="abgelehnt", grund="unvollstaendig", protokoll_eintrag=eintrag)

    aktuelle_menge = repository.aktuelle_menge(fill.titel_id, mode=fill.mode)
    delta = fill.menge if fill.richtung == "kauf" else -fill.menge
    resultierende_menge = aktuelle_menge + delta

    if resultierende_menge < 0:
        eintrag = _protokolliere_ablehnung(
            grund="negative_menge",
            titel_id=fill.titel_id,
            richtung=fill.richtung,
            detail=(
                f"Fill nicht gebucht (AC10): resultierende Menge "
                f"{resultierende_menge} < 0 (Bestand {aktuelle_menge}, "
                f"Fill {fill.richtung} {fill.menge})."
            ),
        )
        return FillErgebnis(status="abgelehnt", grund="negative_menge", protokoll_eintrag=eintrag)

    return FillErgebnis(status="gebucht", fill=fill, resultierende_menge=resultierende_menge)


def _als_str(wert: object) -> str | None:
    return wert if isinstance(wert, str) and wert.strip() else None


def _als_richtung(wert: object) -> Richtung | None:
    return wert if wert in ("kauf", "verkauf") else None


def _protokolliere_ablehnung(
    *,
    grund: FillAblehnungsgrund,
    titel_id: str | None,
    richtung: Richtung | None,
    detail: str,
) -> FillProtokollEintrag:
    eintrag = FillProtokollEintrag(
        zeitpunkt=datetime.now(UTC),
        grund=grund,
        titel_id=titel_id,
        richtung=richtung,
        detail=detail,
    )
    protokolliere(eintrag)
    return eintrag
