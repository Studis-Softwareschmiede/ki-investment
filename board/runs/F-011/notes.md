
## Nachtwächter-Handoff für S-016 (2. Anlauf)
- Spec-Blocker ist gelöst: docs/specs/depot.md v2 definiert jetzt AC12 (Fill→Position-Orchestrierung, Pflichtfeld `modus` echt|simuliert, Mode-Isolation, `strategie_id` statt Name). S-016 implementiert zusätzlich AC12.
- Fertiger, geprüfter Vorarbeits-Stand liegt auf Branch `wip/S-016-gv-rechnung` (app/domain/portfolio/position_buchung.py + Tests) — übernehmen/anpassen statt neu schreiben, danach den wip-Branch löschen.
