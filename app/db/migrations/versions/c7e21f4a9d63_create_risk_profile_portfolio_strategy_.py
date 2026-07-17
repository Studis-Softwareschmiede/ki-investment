"""create risk_profile, portfolio_strategy and portfolio_class_limit tables with 3 presets

Covers (risikomanagement): AC1, AC3, AC4, AC11

Quelle: docs/data-model.md §1 `risk_profile` + `portfolio_strategy` +
`portfolio_class_limit` (C-015), Verträge-Abschnitt "Depotstrategie-
Konfiguration" in docs/specs/risikomanagement.md.

AC1 (Grenzwert-Regelwerk mit mindestens: max. Gewicht je Branche/Sektor
[GICS], max. Gewicht je Anlageklasse, max. Einzelposition, Cash-Quote):
`portfolio_strategy` trägt `max_einzelposition_pct`/`max_sektor_pct`/
`cash_quote_ziel_pct` als je EINEN flachen Wert (das Sektor-Limit gilt
gleichermassen für JEDE GICS-Branche, keine sektor-spezifischen
Einzelwerte — 1:1 aus der Spec-Verträge-Tabelle); `portfolio_class_limit`
trägt das Anlageklassen-Limit als eigene Zeile je (Depotstrategie,
Anlageklasse).

AC3 (3 Risikoprofile als Presets, Nutzer wählt + justiert fein):
`risk_profile` seedet die drei Profile (konservativ/ausgewogen/offensiv,
CHECK-Wertemenge `app.db.models.RISK_PROFILE_NAMES`); `portfolio_strategy`
seedet je Profil GENAU EINE Preset-Zeile (`aktiv=False` — welches Preset
aktiv ist, ist eine Nutzer-Entscheidung, AC3, keine Migrations-/
Coder-Vorwegnahme). Auswahl + Feinjustierung sind
`app.db.depotstrategie.waehle_risikoprofil_preset()`/
`passe_depotstrategie_an()`/`setze_klassen_limit()` (App-Layer).

AC4 (Preset-Grenzwerte sind provisorische, konfigurierbare Defaults:
Einzelposition 2 % [konservativ] .. 10 % [offensiv], Sektor/Branche max
20 %, Anlageklasse Krypto 5-15 % [profilabhängig], Cash-Quote ~5 %): die
Seed-Werte unten übernehmen die von der Spec EXPLIZIT genannten Zahlen
unverändert (2 %/10 % Einzelposition, 20 % Sektor, 5 %/15 % Krypto, 5 %
Cash-Quote). Für das "ausgewogen"-Profil nennt AC4 keinen expliziten
Einzelposition-/Krypto-/Kelly-Cap-Wert — hier bewusst als Mittelwert der
beiden genannten Randwerte interpoliert (5 % Einzelposition, 10 % Krypto,
25 % Kelly-Cap-Gesamtexposure) und im Seed-Kommentar als Interpolation
markiert (keine unbelegte Fabrikation eines dritten, von der Spec nicht
genannten Zahlenbereichs — nur die Mitte des bereits belegten Intervalls).
`gesamt_exposure_cap_pct` (AC10-Kelly-Cap-Spalte, bereits Teil des
bindenden data-model.md-Schemas dieser Tabelle) wird mit dem in AC10
explizit genannten 20-30-%-Bereich befüllt (Rand-/Mittelwerte je Profil) —
die eigentliche Gate-Durchsetzung (AC10) ist NICHT Teil dieser Story.

`portfolio_class_limit` seedet AUSSCHLIESSLICH die Krypto-Zeile (asset_
class_id=7 "Kryptowährungen", siehe `b2bd709be080`-Seed) je Profil — für
die übrigen 10 Anlageklassen nennt weder Konzept noch Spec konkrete
Prozentwerte; sie hier zu erfinden wäre unbelegte Fabrikation (analog zur
Entscheidung in `f908ab5874fe`/`trading_platform`, keine unbelegten
Courtage-/Spread-Zahlen zu seeden). Weitere Klassen-Limits sind spätere,
spec-/nutzergetriebene Konfiguration über `app.db.depotstrategie.
setze_klassen_limit()`.

AC11 (Gate bezieht Limits ausschliesslich aus der Depotstrategie): rein
strukturell durch dieses Schema + `app.db.depotstrategie.
lade_aktive_depotstrategie()` als einzigen Lesepfad unterstützt — das
Risikomanagement-Gate selbst (AC5-AC10) ist ausserhalb dieser Story.

BR-117 (genau eine aktive Depotstrategie, data-model.md §8 Zeile
`portfolio_strategy`): partieller UNIQUE-Index `ux_portfolio_strategy_
aktiv` auf `(aktiv) WHERE aktiv` — bewusst NICHT deferred (analog
`ux_category_weight_version_current`/`ux_analysis_method_version_current`
aus `386f43ae972d`/`8f183aee9753`): die App-seitige Umschaltung
(`app.db.depotstrategie.waehle_risikoprofil_preset()`) deaktiviert die
bisher aktive Zeile IMMER vor der Aktivierung der neuen, beide UPDATEs
laufen sequenziell in derselben Transaktion — zu keinem Zeitpunkt tragen
zwei Zeilen gleichzeitig `aktiv=True`.

`portfolio_class_limit` bewusst OHNE dedizierten `(asset_class_id)`-Index
(data-model.md §8, sql/R05-Ausnahme "analog `risk_profile`/
`portfolio_class_limit`-Stammdatentabellen" — geringe Kardinalität, ein
Full-Table-Scan ist hier günstiger als ein zusätzlicher Index).

Revision ID: c7e21f4a9d63
Revises: f908ab5874fe
Create Date: 2026-07-17 09:00:00.000000

"""

import uuid
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.dialects.postgresql import insert as pg_insert

# revision identifiers, used by Alembic.
revision: str = "c7e21f4a9d63"
down_revision: Union[str, Sequence[str], None] = "f908ab5874fe"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Kryptowährungen (b2bd709be080-Seed) — einzige Anlageklasse, für die AC4
# einen konkreten, profilabhängigen Prozentbereich nennt.
_KRYPTO_ASSET_CLASS_ID = 7

# Deterministische UUIDs (uuid5, stabiler Namensraum) statt server-seitig
# generierter `gen_random_uuid()`-Werte — Voraussetzung für einen
# idempotenten Seed via `ON CONFLICT DO NOTHING (id)` (data-model.md §11
# Punkt 10) UND für die FK-Referenz von `portfolio_strategy` auf
# `risk_profile` sowie von `portfolio_class_limit` auf `portfolio_strategy`
# innerhalb derselben Migration, ohne einen Zwischen-SELECT zu benötigen.
_RISK_PROFILE_IDS = {
    name: uuid.uuid5(uuid.NAMESPACE_URL, f"risk_profile:{name}")
    for name in ("konservativ", "ausgewogen", "offensiv")
}
_PORTFOLIO_STRATEGY_IDS = {
    name: uuid.uuid5(uuid.NAMESPACE_URL, f"portfolio_strategy:{name}")
    for name in ("konservativ", "ausgewogen", "offensiv")
}

RISK_PROFILE_SEED = [
    {"id": _RISK_PROFILE_IDS[name], "name": name}
    for name in ("konservativ", "ausgewogen", "offensiv")
]

# AC4 1:1-Werte (konservativ/offensiv) + interpoliertes "ausgewogen"
# (Mittelwert der beiden Randwerte, siehe Modul-Docstring). `aktiv=False`
# bei allen drei Zeilen: welches Preset aktiv ist, entscheidet der Nutzer
# (AC3), nicht diese Migration.
PORTFOLIO_STRATEGY_SEED = [
    {
        "id": _PORTFOLIO_STRATEGY_IDS["konservativ"],
        "risk_profile_id": _RISK_PROFILE_IDS["konservativ"],
        "max_einzelposition_pct": 2,
        "max_sektor_pct": 20,
        "cash_quote_ziel_pct": 5,
        "gesamt_exposure_cap_pct": 20,
        "aktiv": False,
    },
    {
        "id": _PORTFOLIO_STRATEGY_IDS["ausgewogen"],
        "risk_profile_id": _RISK_PROFILE_IDS["ausgewogen"],
        "max_einzelposition_pct": 5,  # interpoliert (Mittelwert 2 %..10 %)
        "max_sektor_pct": 20,
        "cash_quote_ziel_pct": 5,
        "gesamt_exposure_cap_pct": 25,  # interpoliert (Mittelwert 20 %..30 %)
        "aktiv": False,
    },
    {
        "id": _PORTFOLIO_STRATEGY_IDS["offensiv"],
        "risk_profile_id": _RISK_PROFILE_IDS["offensiv"],
        "max_einzelposition_pct": 10,
        "max_sektor_pct": 20,
        "cash_quote_ziel_pct": 5,
        "gesamt_exposure_cap_pct": 30,
        "aktiv": False,
    },
]

# AC4 Krypto-Bereich 5-15 % (profilabhängig): 5 % konservativ, 15 %
# offensiv 1:1 aus der Spec; 10 % ausgewogen interpoliert (Mittelwert).
PORTFOLIO_CLASS_LIMIT_SEED = [
    {
        "portfolio_strategy_id": _PORTFOLIO_STRATEGY_IDS["konservativ"],
        "asset_class_id": _KRYPTO_ASSET_CLASS_ID,
        "max_klasse_pct": 5,
    },
    {
        "portfolio_strategy_id": _PORTFOLIO_STRATEGY_IDS["ausgewogen"],
        "asset_class_id": _KRYPTO_ASSET_CLASS_ID,
        "max_klasse_pct": 10,  # interpoliert (Mittelwert 5 %..15 %)
    },
    {
        "portfolio_strategy_id": _PORTFOLIO_STRATEGY_IDS["offensiv"],
        "asset_class_id": _KRYPTO_ASSET_CLASS_ID,
        "max_klasse_pct": 15,
    },
]

_ACTIVE_STRATEGY_INDEX = "ux_portfolio_strategy_aktiv"


def upgrade() -> None:
    """Upgrade schema."""
    risk_profile = op.create_table(
        "risk_profile",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("name", sa.String(), nullable=False, unique=True),
        sa.CheckConstraint(
            "name IN ('konservativ', 'ausgewogen', 'offensiv')", name="ck_risk_profile_name"
        ),
    )

    portfolio_strategy = op.create_table(
        "portfolio_strategy",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "risk_profile_id",
            UUID(as_uuid=True),
            sa.ForeignKey("risk_profile.id"),
            nullable=False,
        ),
        sa.Column("max_einzelposition_pct", sa.Numeric(6, 3), nullable=False),
        sa.Column("max_sektor_pct", sa.Numeric(6, 3), nullable=False),
        sa.Column("cash_quote_ziel_pct", sa.Numeric(6, 3), nullable=False),
        sa.Column("gesamt_exposure_cap_pct", sa.Numeric(6, 3), nullable=False),
        sa.Column("aktiv", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.CheckConstraint(
            "max_einzelposition_pct >= 0 AND max_einzelposition_pct <= 100",
            name="ck_portfolio_strategy_max_einzelposition_pct_range",
        ),
        sa.CheckConstraint(
            "max_sektor_pct >= 0 AND max_sektor_pct <= 100",
            name="ck_portfolio_strategy_max_sektor_pct_range",
        ),
        sa.CheckConstraint(
            "cash_quote_ziel_pct >= 0 AND cash_quote_ziel_pct <= 100",
            name="ck_portfolio_strategy_cash_quote_ziel_pct_range",
        ),
        sa.CheckConstraint(
            "gesamt_exposure_cap_pct >= 0 AND gesamt_exposure_cap_pct <= 100",
            name="ck_portfolio_strategy_gesamt_exposure_cap_pct_range",
        ),
    )

    portfolio_class_limit = op.create_table(
        "portfolio_class_limit",
        sa.Column(
            "portfolio_strategy_id",
            UUID(as_uuid=True),
            sa.ForeignKey("portfolio_strategy.id"),
            primary_key=True,
        ),
        sa.Column(
            "asset_class_id",
            sa.SmallInteger(),
            sa.ForeignKey("asset_class.id"),
            primary_key=True,
        ),
        sa.Column("max_klasse_pct", sa.Numeric(6, 3), nullable=False),
        sa.CheckConstraint(
            "max_klasse_pct >= 0 AND max_klasse_pct <= 100",
            name="ck_portfolio_class_limit_max_klasse_pct_range",
        ),
    )

    # BR-117: genau eine aktive Depotstrategie (data-model.md §8) — NICHT
    # deferred, siehe Modul-Docstring.
    op.execute(
        f"""
        CREATE UNIQUE INDEX {_ACTIVE_STRATEGY_INDEX}
        ON portfolio_strategy (aktiv)
        WHERE aktiv
        """
    )

    # Idempotenter Seed (data-model.md §11 Punkt 10: "ON CONFLICT DO NOTHING") —
    # ein wiederholtes `alembic upgrade head` gegen eine bereits geseedete DB
    # darf keine IntegrityError werfen und die Zeilenzahl nicht verändern.
    op.execute(
        pg_insert(risk_profile)
        .values(RISK_PROFILE_SEED)
        .on_conflict_do_nothing(index_elements=["id"])
    )
    op.execute(
        pg_insert(portfolio_strategy)
        .values(PORTFOLIO_STRATEGY_SEED)
        .on_conflict_do_nothing(index_elements=["id"])
    )
    op.execute(
        pg_insert(portfolio_class_limit)
        .values(PORTFOLIO_CLASS_LIMIT_SEED)
        .on_conflict_do_nothing(index_elements=["portfolio_strategy_id", "asset_class_id"])
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table("portfolio_class_limit")
    op.execute(f"DROP INDEX IF EXISTS {_ACTIVE_STRATEGY_INDEX}")
    op.drop_table("portfolio_strategy")
    op.drop_table("risk_profile")
