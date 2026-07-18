"""Modul-Verträge Control-Plane (Story S-074, `docs/specs/frontend-cockpit.md`
AC20/AC21; architecture.md §4 "Control-Plane (schreibend, klar getrennt)").

architecture.md §2 P2 ("Explizite Modul-Verträge"): die Request-Bodies der
POST-Endpunkte in `app/api/control.py` (AC20: "Alle schreibenden
Betriebseingriffe ... laufen ausschliesslich über POSTs in
`app/api/control.py`"):

- `AnlageklassenToggleAnfrage` — der Body von `POST /api/control/
  anlageklassen/{asset_class_id}/toggle` (→ BR-017/BR-018): der neue
  Toggle-Zustand einer Anlageklasse.
- `ModusUeberschreibungAnfrage` — der Body von `POST /api/control/modus`
  (→ BR-019): der gewünschte Modus, global (`asset_class_id=None`) oder je
  Anlageklasse. `modus` bleibt bewusst der volle `Modus`-Wertebereich
  (`echt|simuliert`, `app.contracts.depot.Modus`) statt eines engeren
  `Literal["simuliert"]` — die MVP-Live-Sperre (AC21, BR-019) ist eine
  LAUFZEIT-Regel, die über `app.domain.execution.order_ausfuehrung
  .bestimme_wirksamen_modus` (S-047-Zustandslogik, Wiederverwendung statt
  Duplikat) validiert wird, nicht über eine engere Typgrenze — ein
  ablehnter Versuch (`modus="echt"`) soll als fachlicher 409-Fehler
  sichtbar werden, nicht als generische 422-Typvalidierung (Spec-Wortlaut
  "409 je nach Zustandsmaschinen-Verstoß").
- `KillSwitchAusloesungsAnfrage` — der Body von `POST /api/control/
  kill-switch/ausloesen` (→ BR-021): der Klartext-Grund der manuellen
  Auslösung (`app.contracts.betriebssicherung.KillSwitchAusloeser.grund`).
  `quelle="manuell"` und `zeitstempel` werden vom Router selbst gesetzt
  (nicht vom Aufrufer beeinflussbar — ein Client soll weder eine fremde
  Quelle vortäuschen noch einen Zeitpunkt in der Vergangenheit/Zukunft
  fälschen können, AC11-Protokoll-Integrität).

`POST /api/control/kill-switch/freigeben` (→ BR-021, AC3) trägt keinen
eigenen Body — die Freigabe ist immer dieselbe Aktion, ohne
Auslöser-Metadaten (analog `app.core.kill_switch.freigeben()`).

- `ModusKonfigurationResponse` — die Response von `POST /api/control/modus`:
  dieselben zwei Felder wie `app.contracts.ausfuehrung_paper
  .ModusKonfiguration` (S-047), aber mit einem PLAIN `dict` statt
  `MappingProxyType` für `modus_je_anlageklasse`. Das S-047-Original härtet
  dieses Feld bewusst per `field_validator` auf `MappingProxyType`, um eine
  nachträgliche Mutation zu verhindern (Sicherheits-Review-Fix,
  AC3/BR-019) — für eine reine JSON-Response ist es deshalb NICHT direkt
  als `response_model` geeignet: `mappingproxy` ist kein von pydantics
  JSON-Serializer bekannter Typ (empirisch reproduzierter
  `PydanticSerializationError: Unable to serialize unknown type:
  <class 'mappingproxy'>` beim direkten Einsatz als `response_model`)."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from app.contracts.ausfuehrung_paper import ModusKonfiguration
from app.contracts.depot import Modus


class AnlageklassenToggleAnfrage(BaseModel):
    """AC20 (→ BR-017/BR-018): der gewünschte Toggle-Zustand einer
    Anlageklasse."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    aktiv: bool


class ModusUeberschreibungAnfrage(BaseModel):
    """AC20/AC21 (→ BR-019): der gewünschte Modus-Override — global, wenn
    `asset_class_id` fehlt/`None` ist, sonst für genau diese Anlageklasse
    (Spec A1: "global und je Klasse überschreibbar")."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    modus: Modus
    asset_class_id: int | None = Field(default=None, ge=1, le=11)


class KillSwitchAusloesungsAnfrage(BaseModel):
    """AC20 (→ BR-021): der Klartext-Grund einer manuellen Kill-Switch-
    Auslösung — Pflichtfeld (AC11-Protokoll verlangt einen Grund)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    grund: str = Field(min_length=1)


class ModusKonfigurationResponse(BaseModel):
    """AC20/AC21: JSON-serialisierbares Response-Gegenstück zu
    `app.contracts.ausfuehrung_paper.ModusKonfiguration` (siehe
    Moduldocstring für die `MappingProxyType`-Begründung)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    global_modus: Modus
    modus_je_anlageklasse: dict[int, Modus]

    @classmethod
    def aus_konfiguration(cls, konfiguration: ModusKonfiguration) -> ModusKonfigurationResponse:
        """Baut die Response aus der (intern `MappingProxyType`-gehärteten)
        `ModusKonfiguration`, die `app.core.modus_override` zurückgibt."""
        return cls(
            global_modus=konfiguration.global_modus,
            modus_je_anlageklasse=dict(konfiguration.modus_je_anlageklasse),
        )
