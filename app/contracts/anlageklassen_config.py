"""Modul-Verträge Anlageklassen-Konfiguration — Toggle-Guard (Story S-019,
Spec `docs/specs/anlageklassen-config.md` AC4/AC5).

Deckt exakt den in der Spec genannten "Konsumenten-Kontrakt Toggle": jedes
nachgelagerte Modul (Kandidatensuche, Datenquellen-Abfrage, Analyse,
Handelsplattformen, Depotstrategie — architecture.md §3 Module 2–4/7/8/12/15)
fragt für eine Anlageklasse den Aktiv-Zustand + eine etwaige offene Position
ab und erhält daraus abgeleitet, welche Aktionen erlaubt sind.

- `ToggleZustand` — Eingabe für den Guard: `aktiv` (Toggle-Zustand aus
  S-003/`AssetClass.aktiv`) + `hat_offene_positionen` (Fachwissen des
  jeweiligen Konsumenten — die Positions-Domäne selbst existiert in dieser
  Codebasis noch nicht, analog `app.core.kill_switch`/
  `tests/architecture/test_order_pfad_invariante.py` Cold-Start-Konvention).
- `Verarbeitungserlaubnis` — Output des Guards (AC4/AC5): genau die zwei
  Buckets, auf die sich alle fünf Konsumenten-Module laut AC5-Wortlaut
  ("neue Käufe" vs. "Überwachung und Exit-Ausführung") reduzieren.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class ToggleZustand(BaseModel):
    """Eingabe des Toggle-Guards (Verträge "Konsumenten-Kontrakt Toggle").

    `aktiv` ist der persistente Toggle-Zustand einer Anlageklasse
    (`AssetClass.aktiv`, S-003/AC12). `hat_offene_positionen` markiert, ob
    aktuell mindestens eine gehaltene Position dieser Klasse besteht — der
    Guard selbst ermittelt das nicht (keine Positions-Domäne vorhanden,
    Cold-Start); der jeweilige Konsument liefert diesen Fachwert."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    aktiv: bool
    hat_offene_positionen: bool = False


class Verarbeitungserlaubnis(BaseModel):
    """Entscheid des Toggle-Guards (AC4/AC5) — von jedem nachgelagerten
    Modul (Kandidatensuche, Datenquellen-Abfrage, Analyse,
    Handelsplattformen, Depotstrategie) vor jeder Aktion für eine
    Anlageklasse abzufragen.

    - `neue_verarbeitung_erlaubt` — neue Käufe, neue Kandidatensuche und der
      dafür nötige externe Datenabruf (AC4: "insbesondere wird für eine
      inaktive Klasse keine externe Datenquelle abgefragt"). `False` sobald
      `aktiv = False`, unabhängig von offenen Positionen — eine inaktive
      Klasse ohne offene Positionen hat entsprechend BEIDE Felder `False`
      (Edge-Case "sofort keinerlei Verarbeitung/Datenabruf").
    - `bestandspflege_erlaubt` — Überwachung (Wiederbewertung) UND
      Exit-Ausführung (Verkäufe) bestehender Positionen dieser Klasse,
      inklusive des dafür nötigen Datenabrufs (AC5, deckt A1; BR-018 der
      architecture.md). Bleibt `True`, solange offene Positionen bestehen —
      auch wenn `aktiv = False` ("ein Toggle darf niemals dazu führen, dass
      eine gehaltene Position unüberwacht bleibt").
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    neue_verarbeitung_erlaubt: bool
    bestandspflege_erlaubt: bool
