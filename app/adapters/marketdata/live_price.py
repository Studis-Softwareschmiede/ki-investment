"""Implementierung des `LivePriceProvider`-Ports (Modul 16 Depotmodul,
`docs/specs/depot.md` AC11, S-054; architecture.md §4 `app/adapters/
marketdata/`, P5 "Live-Kurs als Cross-Cutting-Service").

Der eigentliche Live-Kurs-Socket-Adapter (Anbindung an einen Broker-Feed
über `app.adapters.sockets.base.SocketAdapter`) ist NICHT Teil dieser
Story — kein registrierter Socket liefert aktuell laufende Kurse (nur
`app.adapters.sockets.fred.FredAdapter`, makroökonomische Indikatoren,
S-050). `NoOpLivePriceProvider` ist daher bewusst die aktuell einzige
Implementierung: sie liefert für jeden Titel `None` ("kein aktueller Kurs
vorhanden") — analog zum bestehenden Muster in
`app.domain.portfolio.ports.ExitRegelnBestand` (liefert `None`-Felder,
solange keine `exit_rule`-Zeile existiert). Das Depot-Dashboard
(`app.api.dashboard`) behandelt `None` gemäss `depot.md` Edge-Cases als
"nicht bewertbar" statt eines veralteten Werts — kein Fehler, keine
Fiktion eines Kurses."""

from __future__ import annotations

from decimal import Decimal


class NoOpLivePriceProvider:
    """Platzhalter-`LivePriceProvider` (S-054): liefert für jeden Titel
    `None`, bis ein echter Live-Kurs-Socket-Adapter (eigene Story) verdrahtet
    ist."""

    def aktueller_preis(self, titel_id: str) -> Decimal | None:
        return None
