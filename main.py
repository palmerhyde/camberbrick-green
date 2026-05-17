"""
Camberbrick Green — FastAPI application entry point.
"""

from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from contextlib import asynccontextmanager

from database import init_db
from routers import identify, parts, collection, lookup, storage, library


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
app.include_router(library.router)


# ── Page routes ────────────────────────────────────────────────────────────────
@app.get("/")
async def scan(request: Request):
    return templates.TemplateResponse("scan.html", {"request": request})



@app.get("/health")
async def health():
    return {"status": "ok", "app": "Camberbrick Green"}
