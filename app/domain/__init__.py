"""Domain-Layer (architecture.md §4: "REINER KERN — keine I/O, kein LLM,
kein FastAPI, kein SQLAlchemy", P1/P3).

`app/domain/**` darf laut Boundary-Regel NICHT `fastapi`, `sqlalchemy`,
`redis`, `app.adapters.*`, `app.api.*`, `app.db.*` oder `app.scheduler.*`
importieren (Import-Linter/Grep-prüfbar). Dieses Paket enthält bisher
(S-014) nur `no_evidence_no_trade` — die weiteren, in architecture.md §4
gelisteten Domain-Pakete (`scoring`, `sizing`, `risk`, ...) folgen in
späteren Stories.
"""

from __future__ import annotations
