"""Tests für den Keyword-/Ereignis-Filter (Story S-033).

Covers (depot-ueberwachung): AC4

`app.domain.depot_ueberwachung.ereignis_filter.filtere_relevante_news`
lässt nur News durch, deren Text mindestens eines der konfigurierten
Stichworte enthält (Default-Auslöser-Menge), und entdoppelt Duplikate
desselben Ereignisses."""

from __future__ import annotations

from datetime import UTC, datetime

from app.contracts.depot_ueberwachung import DEFAULT_EREIGNIS_KEYWORDS, RohNewsEreignis
from app.domain.depot_ueberwachung.ereignis_filter import filtere_relevante_news

_JETZT = datetime(2026, 7, 17, 12, 0, tzinfo=UTC)


def _news(titel_id: str, text: str, quelle: str = "NewsAPI") -> RohNewsEreignis:
    return RohNewsEreignis(titel_id=titel_id, text=text, quelle=quelle, beobachtet_am=_JETZT)


def test_default_keywords_decken_alle_fuenf_auslöser_ab() -> None:
    """@trace depot-ueberwachung#AC4 — Default-Auslöser-Menge (provisorisch)
    enthält genau die fünf in der Spec genannten Stichworte."""
    assert DEFAULT_EREIGNIS_KEYWORDS == (
        "Insolvenz",
        "Hack",
        "Übernahme",
        "Gewinnwarnung",
        "Downgrade",
    )


def test_news_mit_relevantem_stichwort_wird_durchgelassen() -> None:
    """@trace depot-ueberwachung#AC4 — eine News, die (case-insensitiv)
    eines der konfigurierten Stichworte enthält, gilt als material
    relevant."""
    eintrag = _news("AAPL", "Firma meldet insolvenz nach Liquiditätsengpass")
    ergebnis = filtere_relevante_news([eintrag])
    assert ergebnis == (eintrag,)


def test_news_ohne_relevantes_stichwort_wird_herausgefiltert() -> None:
    """@trace depot-ueberwachung#AC4 — eine News ohne Treffer gegen die
    Stichwortliste wird NICHT durchgelassen (kein Einheitsfilter, der
    alles durchlässt)."""
    eintrag = _news("AAPL", "Quartalszahlen leicht über den Erwartungen")
    assert filtere_relevante_news([eintrag]) == ()


def test_duplikate_desselben_ereignisses_werden_entdoppelt() -> None:
    """@trace depot-ueberwachung#AC4 — zwei identische News desselben
    Titels (gleicher Text) werden zu EINEM Treffer entdoppelt."""
    a = _news("AAPL", "Hack bei Cloud-Anbieter betrifft AAPL-Infrastruktur", quelle="A")
    b = _news("AAPL", "Hack bei Cloud-Anbieter betrifft AAPL-Infrastruktur", quelle="B")
    ergebnis = filtere_relevante_news([a, b])
    assert ergebnis == (a,)


def test_gleicher_text_unterschiedlicher_titel_bleibt_getrennt() -> None:
    """@trace depot-ueberwachung#AC4 — Entdopplung ist titelbezogen: der
    gleiche Text zu ZWEI verschiedenen Titeln erzeugt zwei Treffer."""
    a = _news("AAPL", "Übernahme-Gerücht kursiert am Markt")
    b = _news("MSFT", "Übernahme-Gerücht kursiert am Markt")
    ergebnis = filtere_relevante_news([a, b])
    assert ergebnis == (a, b)


def test_konfigurierbare_stichwortliste_ersetzt_default() -> None:
    """@trace depot-ueberwachung#AC4 — die Filter-Stichwortliste ist als
    Parameter konfigurierbar: ein eigenes Stichwort matcht, obwohl es
    nicht in der Default-Menge enthalten ist; die Default-Menge selbst
    matcht dann nicht mehr, wenn sie nicht mit übergeben wird."""
    eintrag = _news("AAPL", "Regulator verhängt Bussgeld gegen AAPL")
    assert filtere_relevante_news([eintrag], keywords=("Bussgeld",)) == (eintrag,)
    assert filtere_relevante_news([eintrag], keywords=("Hack",)) == ()


def test_leere_news_liste_liefert_leeres_ergebnis() -> None:
    """@trace depot-ueberwachung#AC4 — A2-Analogie: keine News, kein
    Treffer."""
    assert filtere_relevante_news([]) == ()
