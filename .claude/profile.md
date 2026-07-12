# Projekt-Profil — ki-investment
language: python
domains: []
frameworks: ["fastapi"]
build: "uv"
db_dialect: postgres
db_migration_tool: alembic
companions: [redis]
test: "uv run pytest"
lint: "uv run ruff check ."
smoke: "curl -fsS -o /dev/null -w '%{http_code}' http://localhost:8080/health"
merge_policy: pr
cost_mode: balanced
default_branch: main
board: file
obsidian_source: /Users/alex/Library/Mobile Documents/iCloud~md~obsidian/Documents/AlexSecondBrain/300 Projekte/KI Investment
deploy: docker
image: ghcr.io/studis-softwareschmiede/ki-investment
registry: ghcr
container_port: 8080

sonar:
  edition: none
  organization: ""
  project_key: ""
  host_url: ""

adoption_validated_at: 2026-07-12
adoption_validated_dialect: postgres
adoption_validated_companions: [redis]
