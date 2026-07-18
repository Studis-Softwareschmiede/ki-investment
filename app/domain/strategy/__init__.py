"""Strategie, Zeithorizont & Exit-Regel-Fixierung beim Kauf
(architecture.md §4 `domain/strategy/`, Modul 11, Spec
`docs/specs/strategie-exit-regeln.md`).

`attribut_fixierung.py` (Story S-040, AC1/AC11) deckt den reinen
Domain-Kern der **Attribut-Bündel-Fixierung**: fasst Ordergrösse,
Strategie, Zeithorizont, Exit-Regeln und Kauf-These zu einer
`AnnotierteKaufOrder` zusammen und prüft dabei die Vollständigkeit des
Exit-Regel-Teils (AC11, Edge-Case „Fehlende oder unvollständige
Exit-Regeln … verhindern die Weitergabe an das Risikomanagement").

Die session-basierte Vorbereitung (Cluster-Freischaltung, S-037; Default-
Exit-Set-Ableitung, S-038) lebt bewusst NICHT hier, sondern in
`app.db.strategie_katalog`/`app.db.exit_regel_ableitung` — dieses Paket
nimmt deren bereits aufgelöste Ergebnisse als primitive Werte entgegen
(architecture.md §4 P1: `app/domain/**` importiert kein SQLAlchemy/`app.db.*`).

Die eigentliche DB-Persistenz des Exit-Regel-Teils (`exit_rule`-Zeile,
BR-111/BR-137-Unveränderlichkeit) findet NICHT hier, sondern in
`app.adapters.repositories.position_repository
.SqlAlchemyPositionRepository.lege_position_an` statt — siehe
`app.contracts.strategie_exit_regeln`-Moduldocstring für die Abgrenzung
der beiden S-040-Teile (AC1 DB-Fixierung vs. AC11 Vor-Order-Annotierung).
"""

from __future__ import annotations
