"""Tests für `app.db.session` (App-Runtime-DB-Engine/-Session, Story S-054,
`docs/specs/depot.md` AC11) + `app.db.utils.build_db_url` (verschoben aus
`app.db.migrations.env`, S-054, "bei Mehrfachnutzung verschieben").

Covers (depot): AC11
"""

from __future__ import annotations

import pytest

from app.db import session as session_module
from app.db.utils import build_db_url


def test_build_db_url_bricht_bei_fehlenden_pflichtvariablen_ab(monkeypatch):
    for var in (
        "DB_NAME",
        "POSTGRES_DB",
        "DB_USER",
        "POSTGRES_USER",
        "DB_PASSWORD",
        "POSTGRES_PASSWORD",
    ):
        monkeypatch.delenv(var, raising=False)

    with pytest.raises(RuntimeError, match="DB_NAME/POSTGRES_DB"):
        build_db_url()


def test_build_db_url_baut_url_aus_db_praefix_env_vars(monkeypatch):
    monkeypatch.setenv("DB_NAME", "ki_investment")
    monkeypatch.setenv("DB_USER", "app")
    monkeypatch.setenv("DB_PASSWORD", "secret")
    monkeypatch.setenv("DB_HOST", "db-host")
    monkeypatch.setenv("DB_PORT", "5433")

    assert build_db_url() == "postgresql+psycopg://app:secret@db-host:5433/ki_investment"


def test_get_session_liefert_session_und_schliesst_sie_im_finally(monkeypatch):
    """fastapi/A04: Code vor `yield` läuft vor dem Endpunkt, Code danach
    (hier `finally: session.close()`) danach — unabhängig davon, ob der
    Generator normal oder per Exception beendet wird."""
    aufrufe: list[str] = []

    class _FakeSession:
        def __init__(self, engine):
            aufrufe.append("init")

        def close(self):
            aufrufe.append("close")

    monkeypatch.setattr(session_module, "get_engine", lambda: object())
    monkeypatch.setattr(session_module, "Session", _FakeSession)

    generator = session_module.get_session()
    gelieferte_session = next(generator)

    assert isinstance(gelieferte_session, _FakeSession)
    assert aufrufe == ["init"]

    with pytest.raises(StopIteration):
        next(generator)

    assert aufrufe == ["init", "close"]
