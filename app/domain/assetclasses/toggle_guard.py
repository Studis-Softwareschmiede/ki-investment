"""Toggle-Guard — Konsumenten-Kontrakt für den Anlageklassen-Toggle (Story
S-019, Spec `docs/specs/anlageklassen-config.md` AC4/AC5).

Reiner Domain-Kern (architecture.md §4 P1/P3): keine I/O, kein SQLAlchemy,
kein FastAPI. `pruefe_verarbeitungserlaubnis` ist die eine Stelle, die die
AC4/AC5-Regel implementiert — jedes der fünf in der Spec genannten
Konsumenten-Module (Kandidatensuche, Datenquellen-Abfrage, Analyse,
Handelsplattformen, Depotstrategie) fragt sie vor jeder Aktion für eine
Anlageklasse ab, statt die Regel selbst nachzubauen (BR-017/BR-018 der
architecture.md).

**Regel (AC4/AC5):**
- `aktiv = True` → beide Buckets erlaubt (Normalbetrieb).
- `aktiv = False`, keine offenen Positionen → beide Buckets gesperrt
  ("sofort keinerlei Verarbeitung/Datenabruf", Edge-Case der Spec).
- `aktiv = False`, offene Positionen vorhanden → neue Verarbeitung gesperrt
  (keine neuen Käufe/keine neue Kandidatensuche), Bestandspflege
  (Überwachung + Exit-Ausführung der offenen Positionen, inkl. dafür
  nötigem Datenabruf) bleibt erlaubt (AC5, deckt A1: "ein Toggle darf
  niemals dazu führen, dass eine gehaltene Position unüberwacht bleibt").

**Reaktivierung (Edge-Case der Spec):** die Funktion ist zustandslos/rein —
ein erneuter Aufruf mit `aktiv=True` liefert sofort wieder
`neue_verarbeitung_erlaubt=True`, ohne je eine "rückwirkende Verarbeitung"
der Inaktiv-Phase nachzuholen (es gibt schlicht keinen internen Zustand, der
etwas nachholen könnte)."""

from __future__ import annotations

from app.contracts.anlageklassen_config import ToggleZustand, Verarbeitungserlaubnis


def pruefe_verarbeitungserlaubnis(zustand: ToggleZustand) -> Verarbeitungserlaubnis:
    """AC4/AC5: leitet aus dem Toggle-Zustand einer Anlageklasse ab, welche
    Aktionen einem Konsumenten-Modul aktuell erlaubt sind (siehe
    Modul-Docstring für die volle Regel)."""
    return Verarbeitungserlaubnis(
        neue_verarbeitung_erlaubt=zustand.aktiv,
        bestandspflege_erlaubt=zustand.aktiv or zustand.hat_offene_positionen,
    )
