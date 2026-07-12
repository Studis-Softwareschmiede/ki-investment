"""Tests für den Secret-Store mit strikter Paper/Live-Trennung (Story S-008).

Covers (betriebssicherung): AC6

`app.core.secrets.resolve_secret_store_zugang` löst Zugangsdaten für einen
Dienst NIE hartkodiert auf, sondern ausschließlich über Umgebungsvariablen,
und trennt `paper`/`live` durch vollständig getrennte Env-Var-Namensräume
(kein gemeinsamer Basisname, kein Fallback von einer Umgebung auf die
andere). Deckt: erfolgreiche Auflösung je Umgebung (AC6), dass eine
`paper`-Konfiguration NIE die `live`-Werte liest und umgekehrt (Kern von
AC6), fehlende/unvollständige Einträge (`SecretStoreFehler`, kein stiller
Fallback) sowie dass die aufgelösten Zugangsdaten nie im Klartext in
`repr()`/`str()` erscheinen (NFR "keine Secrets im Klartext in Logs oder
Alerts").
"""

from __future__ import annotations

import pytest

from app.core.secrets import SecretStoreFehler, resolve_secret_store_zugang


def test_resolve_secret_store_zugang_liest_paper_env_vars() -> None:
    """@trace betriebssicherung#AC6 — löst Endpunkt/API-Key aus den
    `<DIENST>_PAPER_*`-Env-Variablen auf."""
    env = {
        "IBKR_PAPER_ENDPOINT": "https://paper.example.test",
        "IBKR_PAPER_API_KEY": "paper-key-123",  # gitleaks:allow
    }
    zugang = resolve_secret_store_zugang("ibkr", "paper", env=env)
    assert zugang.dienst == "ibkr"
    assert zugang.umgebung == "paper"
    assert zugang.endpunkt == "https://paper.example.test"
    assert zugang.api_key == "paper-key-123"
    assert zugang.api_secret is None


def test_resolve_secret_store_zugang_liest_live_env_vars_getrennt() -> None:
    """@trace betriebssicherung#AC6 — `live` liest aus einem eigenen,
    unabhängigen Namensraum (`<DIENST>_LIVE_*`), nicht aus den
    `paper`-Variablen."""
    env = {
        "IBKR_LIVE_ENDPOINT": "https://live.example.test",
        "IBKR_LIVE_API_KEY": "live-key-456",  # gitleaks:allow
        "IBKR_LIVE_API_SECRET": "live-secret-789",  # gitleaks:allow
    }
    zugang = resolve_secret_store_zugang("ibkr", "live", env=env)
    assert zugang.umgebung == "live"
    assert zugang.endpunkt == "https://live.example.test"
    assert zugang.api_key == "live-key-456"
    assert zugang.api_secret == "live-secret-789"


def test_paper_konfiguration_laeuft_nie_gegen_live_endpunkt() -> None:
    """@trace betriebssicherung#AC6 — Kern-Anforderung: sind BEIDE
    Umgebungen für denselben Dienst konfiguriert, liefert die Auflösung
    für `paper` niemals den `live`-Endpunkt/-Key (und umgekehrt), auch
    wenn beide gleichzeitig in der Umgebung vorhanden sind."""
    env = {
        "IBKR_PAPER_ENDPOINT": "https://paper.example.test",
        "IBKR_PAPER_API_KEY": "paper-key-123",  # gitleaks:allow
        "IBKR_LIVE_ENDPOINT": "https://live.example.test",
        "IBKR_LIVE_API_KEY": "live-key-456",  # gitleaks:allow
    }
    paper_zugang = resolve_secret_store_zugang("ibkr", "paper", env=env)
    live_zugang = resolve_secret_store_zugang("ibkr", "live", env=env)

    assert paper_zugang.endpunkt != live_zugang.endpunkt
    assert paper_zugang.api_key != live_zugang.api_key
    assert paper_zugang.endpunkt == "https://paper.example.test"
    assert live_zugang.endpunkt == "https://live.example.test"


def test_fehlender_secret_store_eintrag_wirft_ohne_fallback() -> None:
    """@trace betriebssicherung#AC6 — fehlt der vollständige Eintrag für
    die angeforderte Umgebung, wird `SecretStoreFehler` geworfen — es gibt
    KEINEN stillen Rückfall auf die jeweils andere Umgebung, selbst wenn
    diese vollständig konfiguriert ist."""
    env = {
        "IBKR_PAPER_ENDPOINT": "https://paper.example.test",
        "IBKR_PAPER_API_KEY": "paper-key-123",  # gitleaks:allow
    }
    with pytest.raises(SecretStoreFehler):
        resolve_secret_store_zugang("ibkr", "live", env=env)


def test_leerer_api_key_zaehlt_als_fehlend() -> None:
    """@trace betriebssicherung#AC6 — ein leerer String für den API-Key
    wird wie ein fehlender Eintrag behandelt (kein "leeres" Secret als
    gültig akzeptiert)."""
    env = {
        "IBKR_PAPER_ENDPOINT": "https://paper.example.test",
        "IBKR_PAPER_API_KEY": "",
    }
    with pytest.raises(SecretStoreFehler):
        resolve_secret_store_zugang("ibkr", "paper", env=env)


def test_aufgeloester_zugang_zeigt_secrets_nie_im_klartext_in_repr() -> None:
    """@trace betriebssicherung#AC6 — `repr()`/`str()` des aufgelösten
    Zugangs enthalten den API-Key/das API-Secret NIE im Klartext (NFR:
    "keine Secrets im Klartext in Logs oder Alerts") — nur nicht-sensible
    Felder (Dienst, Umgebung, Endpunkt) sind sichtbar."""
    env = {
        "IBKR_PAPER_ENDPOINT": "https://paper.example.test",
        "IBKR_PAPER_API_KEY": "dummy-fixture-secret-42",  # gitleaks:allow
    }
    zugang = resolve_secret_store_zugang("ibkr", "paper", env=env)

    dargestellt = repr(zugang) + str(zugang)
    assert "dummy-fixture-secret-42" not in dargestellt
    assert "ibkr" in dargestellt
    assert "paper" in dargestellt
