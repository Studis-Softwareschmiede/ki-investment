"""Tests für den Socket-Adapter-Port (Story S-005).

Covers (dateneingang): AC1, AC2

`app.adapters.sockets.base.SocketAdapter` ist die Basisklasse/der Port, von
der jeder konkrete Quellen-Adapter erbt (AC1). Diese Tests verwenden zwei
schlanke Fake-Adapter mit bewusst unterschiedlichem Rohantwort-Format, um
zu zeigen, dass `fetch()` für BEIDE Quellen identisch strukturierte
`Datenpunkt`-Instanzen liefert (AC1) und ungültige Kandidaten (fehlende
Pflicht-Metadaten) verwirft, statt sie zu schätzen (AC2). Die konkrete
FRED-Referenzimplementierung wird separat in `test_fred.py` getestet.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import Any

from app.adapters.sockets.base import SocketAdapter
from app.contracts.dateneingang import Datenpunkt


class _FakeAdapterMitListenRohformat(SocketAdapter):
    """Fake-Quelle A: Rohantwort ist eine Liste von (Wert, Qualität)-Tupeln."""

    quelle_name = "fake-a"

    def __init__(self, rohantwort: list[tuple[Any, str | None]]) -> None:
        super().__init__()
        self._rohantwort = rohantwort

    async def _fetch_raw(self) -> list[tuple[Any, str | None]]:
        return self._rohantwort

    def _normalize(self, rohantwort: list[tuple[Any, str | None]]) -> list[dict[str, Any]]:
        return [
            {
                "wert": wert,
                "quelle": self.quelle_name,
                "timestamp": datetime(2026, 7, 1, tzinfo=UTC),
                "anlageklassen_tag": 1,
                "qualitaetsindikator": qualitaetsindikator,
            }
            for wert, qualitaetsindikator in rohantwort
        ]


class _FakeAdapterMitDictRohformat(SocketAdapter):
    """Fake-Quelle B: Rohantwort ist ein verschachteltes Dict — bewusst ein
    ANDERES Rohformat als Quelle A, damit AC1 (quellen-unabhängig
    identische Struktur) nicht durch zufällige Formatgleichheit
    vorgetäuscht wird."""

    quelle_name = "fake-b"

    def __init__(self, rohantwort: dict[str, Any]) -> None:
        super().__init__()
        self._rohantwort = rohantwort

    async def _fetch_raw(self) -> dict[str, Any]:
        return self._rohantwort

    def _normalize(self, rohantwort: dict[str, Any]) -> list[dict[str, Any]]:
        return [
            {
                "wert": eintrag.get("value"),
                "quelle": self.quelle_name,
                "timestamp": eintrag.get("ts"),
                "anlageklassen_tag": eintrag.get("klasse"),
                "qualitaetsindikator": eintrag.get("qualitaet"),
            }
            for eintrag in rohantwort.get("items", [])
        ]


def test_fetch_liefert_quellenunabhaengig_identisch_strukturierte_datenpunkte() -> None:
    """@trace dateneingang#AC1 — zwei Adapter mit völlig unterschiedlichem
    Rohantwort-Format liefern über `fetch()` `Datenpunkt`-Instanzen mit
    identischer Feldstruktur (gleiche Pflicht-Metadaten-Felder), sodass
    Konsumenten die Quelle nicht kennen müssen."""
    adapter_a = _FakeAdapterMitListenRohformat([(1.23, "roh")])
    adapter_b = _FakeAdapterMitDictRohformat(
        {
            "items": [
                {
                    "value": 4.56,
                    "ts": datetime(2026, 7, 2, tzinfo=UTC),
                    "klasse": 7,
                    "qualitaet": "roh",
                }
            ]
        }
    )

    punkte_a = asyncio.run(adapter_a.fetch())
    punkte_b = asyncio.run(adapter_b.fetch())

    assert len(punkte_a) == 1
    assert len(punkte_b) == 1
    assert isinstance(punkte_a[0], Datenpunkt)
    assert isinstance(punkte_b[0], Datenpunkt)
    assert punkte_a[0].model_fields_set == punkte_b[0].model_fields_set
    assert punkte_a[0].quelle == "fake-a"
    assert punkte_b[0].quelle == "fake-b"
    assert punkte_a[0].anlageklassen_tag == 1
    assert punkte_b[0].anlageklassen_tag == 7


def test_fetch_verwirft_kandidaten_mit_fehlenden_pflicht_metadaten() -> None:
    """@trace dateneingang#AC2 — Kandidaten ohne Qualitätsindikator bzw.
    ohne Timestamp werden von `fetch()` verworfen, statt geschätzt oder mit
    einem Default aufgefüllt an den Aufrufer weitergereicht zu werden."""
    adapter = _FakeAdapterMitDictRohformat(
        {
            "items": [
                {
                    "value": 1.0,
                    "ts": datetime(2026, 7, 1, tzinfo=UTC),
                    "klasse": 1,
                    "qualitaet": "roh",
                },
                {
                    "value": 2.0,
                    "ts": datetime(2026, 7, 1, tzinfo=UTC),
                    "klasse": 1,
                    "qualitaet": None,
                },
                {"value": 3.0, "ts": None, "klasse": 1, "qualitaet": "roh"},
            ]
        }
    )

    punkte = asyncio.run(adapter.fetch())

    assert len(punkte) == 1
    assert punkte[0].wert == 1.0
