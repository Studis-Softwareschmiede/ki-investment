"""Domain-Kern (architecture.md §4): reine Geschäftslogik, keine I/O.

`app/domain/**` darf laut architecture.md §4 Boundary-Regeln NICHT
importieren: `fastapi`, `sqlalchemy`, `redis`, `app.adapters.*`,
`app.api.*`, `app.db.*`, `app.scheduler.*`.
"""

from __future__ import annotations
