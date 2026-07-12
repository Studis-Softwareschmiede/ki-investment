"""alembic env.py — DB-Verbindung ausschliesslich aus Umgebungsvariablen (.env.db-Konvention).

Keine Klartext-Credentials im Repo (projekt-setup.md AC1/Edge-Cases, security/R01):
fehlt eine Pflicht-Variable, bricht das Skript mit einer klaren Fehlermeldung ab,
statt auf einen Default mit echten Zugangsdaten zurueckzufallen.
"""

import os
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# Interpret the config file for Python logging.
# This line sets up loggers basically.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# ORM-Modelle registrieren, damit target_metadata fuer Autogenerate verfuegbar ist.
from app.db import models  # noqa: E402,F401 — Import registriert die Modelle bei Base.metadata
from app.db.base import Base  # noqa: E402

target_metadata = Base.metadata


def _build_db_url() -> str:
    """Baut die DB-URL aus DB_*/POSTGRES_*-Env-Vars (.env.db-Konvention).

    Liest wahlweise die generischen `DB_*`-Namen oder die Compose-Konvention
    `POSTGRES_*` (siehe `.env.db.example`). Fehlt eine Pflicht-Variable in
    beiden Namensschemata, bricht der Start mit Nennung der fehlenden
    Variable ab (kein stiller Fallback auf Default-Credentials).
    """
    name = os.environ.get("DB_NAME") or os.environ.get("POSTGRES_DB")
    user = os.environ.get("DB_USER") or os.environ.get("POSTGRES_USER")
    password = os.environ.get("DB_PASSWORD") or os.environ.get("POSTGRES_PASSWORD")
    host = os.environ.get("DB_HOST", "localhost")
    port = os.environ.get("DB_PORT", "5432")

    missing = [
        env_names
        for value, env_names in (
            (name, "DB_NAME/POSTGRES_DB"),
            (user, "DB_USER/POSTGRES_USER"),
            (password, "DB_PASSWORD/POSTGRES_PASSWORD"),
        )
        if not value
    ]
    if missing:
        raise RuntimeError(
            "Fehlende DB-Umgebungsvariable(n): "
            + ", ".join(missing)
            + " — bitte .env.db setzen (siehe .env.db.example)."
        )

    return f"postgresql+psycopg://{user}:{password}@{host}:{port}/{name}"


config.set_main_option("sqlalchemy.url", _build_db_url())


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    This configures the context with just a URL
    and not an Engine, though an Engine is acceptable
    here as well.  By skipping the Engine creation
    we don't even need a DBAPI to be available.

    Calls to context.execute() here emit the given string to the
    script output.

    """
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode.

    In this scenario we need to create an Engine
    and associate a connection with the context.

    """
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
