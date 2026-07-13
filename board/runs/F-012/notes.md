## S-037 (Done 2026-07-13)
- Gebaut: Katalogtabellen strategy_cluster/strategy/time_horizon (Alembic ddaf9dcc6216, idempotenter Seed: 18 Strategien/4 Cluster, 9 Horizonte mit transaktionskosten_relevanz + break_even_anforderung).
- Nutzen für Folge-Storys: pruefe_cluster_freischaltung() (Cluster-Gate, Laufzeit-konfigurierbar via app_stage) und pruefe_kombination() (Strategie×Horizont) in app/db/strategie_katalog.py — für Exit-Regeln (S-038) direkt wiederverwenden, kein eigenes Gate bauen.
- Achtung: `alembic check` meldet pre-existing Drift NUR bei partitionierten market_data_bronze/silver/gold (bekanntes Autogenerate-Limit seit S-022/S-024) — kein Fehler neuer Migrationen.
- CI läuft nicht auf feature/*-Pushes (build.yml: nur main/master) — Verifikation je Story lokal via Test-Gate; gebündelte CI beim finalen Feature-Merge.
