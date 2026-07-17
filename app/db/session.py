"""App-Runtime-DB-Engine/-Session (Modul 16 Depotmodul, `docs/specs/depot.md`
AC11, S-054) — der erste FastAPI-Endpunkt, der ausserhalb von Tests/Alembic
eine echte DB-Session braucht (`app.main` war bislang reiner Health-Scaffold
ohne DB-Zugriff).

Verwendet dieselbe `.env.db`-Konvention wie `app.db.migrations.env`
(`app.db.utils.build_db_url`, `DB_*`/`POSTGRES_*`-Env-Vars, security/R01:
keine Klartext-Credentials im Repo). Die Engine wird lazily UND genau einmal
pro Prozess aufgebaut (`@lru_cache`, analog `app.config.get_settings`,
fastapi/A06) — `get_session()` ist eine FastAPI-`yield`-Dependency
(fastapi/A04): öffnet je Request eine Session, schliesst sie im
`finally`-Pfad, unabhängig davon, ob der Endpunkt erfolgreich durchläuft
oder eine Exception wirft."""

from __future__ import annotations

from collections.abc import Generator
from functools import lru_cache

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session

from app.db.utils import build_db_url


@lru_cache
def get_engine() -> Engine:
    """Singleton-Engine für den App-Prozess (analog `get_settings()`)."""
    return create_engine(build_db_url())


def get_session() -> Generator[Session, None, None]:
    """FastAPI-`Depends`-Dependency: eine `Session` je Request, im
    `finally`-Pfad geschlossen (fastapi/A04)."""
    session = Session(get_engine())
    try:
        yield session
    finally:
        session.close()
