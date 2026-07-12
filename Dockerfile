# Python-Service (FastAPI/uvicorn) — Multi-Stage, uv
# Muster: offizielle Astral-Doku "Using uv in Docker"
# (https://docs.astral.sh/uv/guides/integration/docker/).
# Projekt-spezifische Zusätze (z.B. Foundry/Anvil-CLI, System-Libs)
# im Projekt-Dockerfile ergänzen — diese Vorlage bleibt generisch.

# --- Build-Stage: Abhängigkeiten via uv gegen pyproject.toml + uv.lock ---
FROM python:3.13-slim AS build

# uv aus dem offiziellen Astral-Image als Layer-Quelle
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# System-Python beider Stages nutzen (kein zusätzlicher Download)
ENV UV_PYTHON_DOWNLOADS=0

WORKDIR /app

# 1) Nur Abhängigkeiten (ohne Projekt) — cachebarer Layer, ändert sich selten
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    uv sync --frozen --no-install-project --no-editable

# 2) Projekt-Quellcode einspielen und synchronisieren
COPY . /app
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-editable

# --- Runtime-Stage: schlank, nur das venv + Quellcode ---
FROM python:3.13-slim

WORKDIR /app

# Nur das fertige venv aus der Build-Stage übernehmen
COPY --from=build /app/.venv /app/.venv
# App-Code (uvicorn lädt app.main:app zur Laufzeit)
COPY --from=build /app/app /app/app

# venv ins PATH — "python"/"uvicorn" kommen aus dem venv
ENV PATH="/app/.venv/bin:$PATH"

EXPOSE 8080
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080"]
