"""Tests für `ist_transienter_fehler` (Story S-020).

Covers (dateneingang): AC10

Klassifiziert Quellenfehler nach AC10 ("Transiente Quellenfehler (HTTP
429, 5xx, Timeout) werden mit Exponential Backoff erneut versucht").
"""

from __future__ import annotations

import urllib.error

import httpx
import pytest

from app.scheduler.errors import ist_transienter_fehler


class _FakeResponse:
    def __init__(self, status_code: int) -> None:
        self.status_code = status_code


class _FakeHttpStatusError(Exception):
    """Duck-Type analog `httpx.HTTPStatusError` (`.response.status_code`)."""

    def __init__(self, status_code: int) -> None:
        super().__init__(f"status {status_code}")
        self.response = _FakeResponse(status_code)


def test_timeout_error_is_transient() -> None:
    """@trace dateneingang#AC10 — ein Timeout gilt als transient."""
    assert ist_transienter_fehler(TimeoutError("timed out")) is True


def test_http_429_is_transient() -> None:
    """@trace dateneingang#AC10 — HTTP 429 (Rate-Limit) gilt als
    transient."""
    exc = urllib.error.HTTPError("http://x", 429, "Too Many Requests", {}, None)
    assert ist_transienter_fehler(exc) is True


def test_http_5xx_is_transient() -> None:
    """@trace dateneingang#AC10 — jeder HTTP-5xx-Statuscode gilt als
    transient."""
    exc = urllib.error.HTTPError("http://x", 503, "Service Unavailable", {}, None)
    assert ist_transienter_fehler(exc) is True


def test_http_404_is_not_transient() -> None:
    """@trace dateneingang#AC10 — ein permanenter Client-Fehler (z. B.
    404) gilt NICHT als transient — kein Retry, keine Dead-Letter-Queue
    durch diese Klassifikation."""
    exc = urllib.error.HTTPError("http://x", 404, "Not Found", {}, None)
    assert ist_transienter_fehler(exc) is False


@pytest.mark.parametrize(
    "exc",
    [
        httpx.TimeoutException("timed out"),
        httpx.ReadTimeout("read timed out"),
        httpx.ConnectTimeout("connect timed out"),
        httpx.PoolTimeout("pool timed out"),
        httpx.WriteTimeout("write timed out"),
    ],
)
def test_httpx_timeout_exceptions_are_transient(exc: httpx.TimeoutException) -> None:
    """@trace dateneingang#AC10 — `httpx`-Timeout-Fehler
    (`TimeoutException` und alle Subklassen: `ReadTimeout`,
    `ConnectTimeout`, `PoolTimeout`, `WriteTimeout`) sind KEINE Subklasse
    des eingebauten `TimeoutError` und tragen kein `.status_code`/`.code`
    — sie müssen trotzdem als transient gelten (AC10: "... Timeout ...")."""
    assert ist_transienter_fehler(exc) is True


def test_httpx_transport_error_is_transient() -> None:
    """@trace dateneingang#AC10 — ein allgemeiner `httpx`-Netzwerkfehler
    (`TransportError`, z. B. Verbindungsabbruch) gilt ebenfalls als
    transient, nicht nur reine Timeouts."""
    assert ist_transienter_fehler(httpx.ConnectError("connection refused")) is True


def test_httpx_http_status_error_is_classified_via_response_status_code() -> None:
    """@trace dateneingang#AC10 — ein echter `httpx.HTTPStatusError`
    (nicht nur der Duck-Type in `_FakeHttpStatusError`) wird über
    `.response.status_code` korrekt klassifiziert."""
    request = httpx.Request("GET", "http://x")
    response_5xx = httpx.Response(503, request=request)
    exc_5xx = httpx.HTTPStatusError("server error", request=request, response=response_5xx)
    assert ist_transienter_fehler(exc_5xx) is True

    response_404 = httpx.Response(404, request=request)
    exc_404 = httpx.HTTPStatusError("not found", request=request, response=response_404)
    assert ist_transienter_fehler(exc_404) is False


def test_duck_typed_status_code_attribute_is_classified() -> None:
    """@trace dateneingang#AC10 — Fehler anderer HTTP-Bibliotheken
    (`.response.status_code`, z. B. httpx-Stil) werden über Duck-Typing
    erkannt, keine harte `httpx`-Abhängigkeit nötig."""
    assert ist_transienter_fehler(_FakeHttpStatusError(500)) is True
    assert ist_transienter_fehler(_FakeHttpStatusError(400)) is False


def test_generic_exception_without_status_is_not_transient() -> None:
    """@trace dateneingang#AC10 — ein Fehler ohne erkennbaren Status/Code
    (z. B. `ValueError` bei einem Parsing-Fehler) gilt als permanent."""
    assert ist_transienter_fehler(ValueError("kaputtes JSON")) is False
