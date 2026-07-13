"""Klassifikation transienter Quellenfehler (AC10, `docs/specs/dateneingang.md`:
"Transiente Quellenfehler (HTTP 429, 5xx, Timeout) werden mit Exponential
Backoff erneut versucht ...").

`ist_transienter_fehler()` entscheidet, ob ein von einem Socket-Adapter
(`app.adapters.sockets.base.SocketAdapter._fetch_raw`) geworfener Fehler
für `app.scheduler.worker.Worker` einen Retry-Kandidaten darstellt (AC10)
oder als endgültiger Fehlschlag gilt (kein Retry, keine Dead-Letter-Queue
— AC10 beschreibt DLQ ausdrücklich nur für erschöpfte TRANSIENTE
Versuche). `httpx` ist eine deklarierte Projekt-Dependency
(`pyproject.toml`, `httpx>=0.28.1`) — dessen Timeout-/Transport-Fehler
(`httpx.TimeoutException`, `ReadTimeout`, `ConnectTimeout`, `PoolTimeout`,
`WriteTimeout`, sowie allgemeiner `httpx.TransportError`) sind KEINE
Subklasse des eingebauten `TimeoutError` und tragen weder `.response`
noch `.status_code`/`.code` — sie werden deshalb explizit erkannt.
Zusätzlich Duck-Typing für andere/eigene HTTP-Fehler: Adapter dürfen
`urllib.error.HTTPError`, `httpx.HTTPStatusError`-artige Fehler
(`.response.status_code`) oder eigene Exceptions mit
`.status_code`/`.code`-Attribut werfen."""

from __future__ import annotations

import urllib.error

import httpx

#: HTTP-Statuscodes, die laut AC10 als transient gelten: 429 (Rate-Limit)
#: und jeder 5xx-Server-/Gateway-Fehler.
_TRANSIENTE_STATUS_CODES = frozenset({429}) | frozenset(range(500, 600))


def ist_transienter_fehler(exc: BaseException) -> bool:
    """AC10: `True` bei Timeout oder HTTP 429/5xx, sonst `False`
    (permanenter Fehler — kein Retry, keine Dead-Letter-Queue durch diese
    Story)."""
    if isinstance(exc, TimeoutError):
        return True
    if isinstance(exc, (httpx.TimeoutException, httpx.TransportError)):
        return True
    if isinstance(exc, urllib.error.HTTPError):
        return exc.code in _TRANSIENTE_STATUS_CODES

    status_code = getattr(getattr(exc, "response", None), "status_code", None)
    if status_code is None:
        status_code = getattr(exc, "status_code", None)
    if status_code is None:
        status_code = getattr(exc, "code", None)
    return isinstance(status_code, int) and status_code in _TRANSIENTE_STATUS_CODES


__all__ = ["ist_transienter_fehler"]
