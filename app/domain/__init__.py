"""Domain-Layer (architecture.md §4: "REINER KERN — keine I/O, kein LLM,
kein FastAPI, kein SQLAlchemy", P1/P3).

`app/domain/**` darf laut Boundary-Regel NICHT `fastapi`, `sqlalchemy`,
`redis`, `app.adapters.*`, `app.api.*`, `app.db.*` oder `app.scheduler.*`
importieren (Import-Linter/Grep-prüfbar). Enthält aktuell
`no_evidence_no_trade` (S-014) und `scoring` (S-009–S-011); weitere
Domain-Pakete aus architecture.md §4 (`sizing`, `risk`, ...) folgen.
"""

from __future__ import annotations
