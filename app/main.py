"""Scaffold-Einstiegspunkt — Health-Endpoint für Smoke/Preview; App-Code folgt via /flow."""
from fastapi import FastAPI

app = FastAPI(title="ki-investment")


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}
