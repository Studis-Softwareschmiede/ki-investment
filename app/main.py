"""Einstiegspunkt — Health-Endpoint für Smoke/Preview + registrierte
API-Router (architecture.md §4 `app/api/`).

Hot-Spot-Konvention (Story S-064): Router-Registrierungen stehen als
zusammenhängender, append-only-freundlicher Block (ein `include_router`
je Zeile) — Folge-Stories ergänzen hier nur je EINE Zeile. Das
StaticFiles-Mount + Jinja2Templates-Setup lebt bewusst NICHT hier, sondern
in `app/web/templates_setup.py` (`configure_web`)."""

from fastapi import FastAPI

from app.api.config import router as config_router
from app.api.control import router as control_router
from app.api.dashboard import router as dashboard_router
from app.api.depot import router as depot_router
from app.api.kandidaten import router as kandidaten_router
from app.api.system_status import router as system_status_router
from app.api.trades import router as trades_router
from app.api.ui import router as ui_router
from app.api.warteliste import router as warteliste_router
from app.web.templates_setup import configure_web

app = FastAPI(title="ki-investment")
configure_web(app)

# --- cockpit routers (append-only) ---
app.include_router(dashboard_router)
app.include_router(depot_router)
app.include_router(ui_router)
app.include_router(trades_router)
app.include_router(config_router)
app.include_router(system_status_router)
app.include_router(kandidaten_router)
app.include_router(control_router)
app.include_router(warteliste_router)
# --- end cockpit routers ---


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}
