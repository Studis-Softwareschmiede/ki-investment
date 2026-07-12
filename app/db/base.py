"""Deklarative SQLAlchemy-Basisklasse — von allen ORM-Modellen in app/db/ geteilt."""

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Gemeinsame Metadata-Registry für alembic-Autogenerate + Modell-Deklaration."""
