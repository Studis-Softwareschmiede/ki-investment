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
# obsidian_source: wird von /agent-flow:from-notes gesetzt
deploy: docker
image: ghcr.io/studis-softwareschmiede/ki-investment
registry: ghcr
container_port: 8080

sonar:
  edition: none
  organization: ""
  project_key: ""
  host_url: ""
