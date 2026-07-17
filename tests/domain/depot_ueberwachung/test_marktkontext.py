"""Tests für die Marktkontext-Normierung von Kursbewegungen (Story S-033).

Covers (depot-ueberwachung): AC5

`app.domain.depot_ueberwachung.marktkontext.normiere_kursbewegung`
bewertet eine Kursbewegung relativ zur gleichzeitigen Marktbewegung
(Übertreibung ggü. dem Markt), statt am Absolutwert — und fällt bei
fehlendem Marktreferenz-Wert konservativ auf die Absolut-Bewertung
zurück (Edge-Case)."""

from __future__ import annotations

from decimal import Decimal

from app.domain.depot_ueberwachung.marktkontext import normiere_kursbewegung


def test_kurssturz_an_starkem_markttag_wird_relativiert() -> None:
    """@trace depot-ueberwachung#AC5 — Spec-Beispiel: -10 % an einem
    -8 %-Markttag normiert auf -2 % (Übertreibung ggü. dem Markt), nicht
    auf den vollen Absolutwert."""
    ergebnis = normiere_kursbewegung(Decimal("-0.10"), Decimal("-0.08"))
    assert ergebnis.normierte_bewegung == Decimal("-0.02")
    assert ergebnis.fallback_verwendet is False


def test_gleicher_kurssturz_an_flachem_markttag_bleibt_voll_bewertet() -> None:
    """@trace depot-ueberwachung#AC5 — Spec-Beispiel: -10 % an einem
    flachen Tag (Markt 0 %) normiert auf den vollen -10 % — löst NICHT
    dieselbe (relativierte) Bewertung aus wie der -8 %-Markttag-Fall."""
    ergebnis = normiere_kursbewegung(Decimal("-0.10"), Decimal("0"))
    assert ergebnis.normierte_bewegung == Decimal("-0.10")
    assert ergebnis.fallback_verwendet is False


def test_titel_faellt_wie_der_markt_ergibt_keine_normierte_abweichung() -> None:
    """@trace depot-ueberwachung#AC5 — ein Titel, der exakt im
    Gleichschritt mit dem Markt fällt, hat eine normierte Bewegung von 0
    (kein titelspezifisches Signal)."""
    ergebnis = normiere_kursbewegung(Decimal("-0.08"), Decimal("-0.08"))
    assert ergebnis.normierte_bewegung == Decimal("0")


def test_fehlender_marktreferenz_wert_faellt_konservativ_auf_absolutwert_zurueck() -> None:
    """@trace depot-ueberwachung#AC5 — Edge-Case: fehlt der
    Marktreferenz-Wert, wird konservativ auf Absolut-Bewertung
    zurückgefallen (`fallback_verwendet=True`), statt den Titel
    unbewertet zu lassen."""
    ergebnis = normiere_kursbewegung(Decimal("-0.10"), None)
    assert ergebnis.normierte_bewegung == Decimal("-0.10")
    assert ergebnis.fallback_verwendet is True
    assert ergebnis.markt_bewegung is None
