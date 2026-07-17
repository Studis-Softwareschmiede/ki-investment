"""Einstiegspunkt — Health-Endpoint für Smoke/Preview + registrierte
API-Router (architecture.md §4 `app/api/`)."""

from fastapi import FastAPI

from app.api.dashboard import router as dashboard_router

app = FastAPI(title="ki-investment")
app.include_router(dashboard_router)


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}
