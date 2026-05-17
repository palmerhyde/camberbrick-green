"""
Camberbrick Green — FastAPI application entry point.
"""

from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from contextlib import asynccontextmanager

from database import init_db
from routers import identify, parts, collection, lookup, storage


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialise the database on startup."""
    init_db()
    yield


app = FastAPI(title="Camberbrick Green", lifespan=lifespan)

app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")

# ── Routers ────────────────────────────────────────────────────────────────────
app.include_router(identify.router)
app.include_router(parts.router)
app.include_router(collection.router)
app.include_router(lookup.router)
app.include_router(storage.router)


# ── Page routes ────────────────────────────────────────────────────────────────
@app.get("/")
async def scan(request: Request):
    return templates.TemplateResponse("scan.html", {"request": request})


@app.get("/library")
async def library(request: Request):
    from routers.collection import _get_part_with_location
    from database import get_db
    conn = get_db()
    try:
        rows = conn.execute("SELECT part_id FROM parts ORDER BY part_id").fetchall()
        parts_list = [_get_part_with_location(conn, r["part_id"]) for r in rows]
    finally:
        conn.close()
    return templates.TemplateResponse("library.html", {
        "request": request,
        "parts":   [p for p in parts_list if p],
    })


@app.get("/health")
async def health():
    return {"status": "ok", "app": "Camberbrick Green"}
