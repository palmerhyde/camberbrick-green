"""
Camberbrick Green — FastAPI application entry point.
"""

import asyncio
from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from contextlib import asynccontextmanager

from database import init_db, get_parts_missing_ba_category, get_db
from routers import identify, parts, collection, lookup, storage, library
from routers.parts import get_brickarchitect_category


async def _refresh_missing_ba_categories():
    """Background task: fetch BA category for any parts that don't have one yet."""
    await asyncio.sleep(2)  # let the server finish starting
    part_ids = get_parts_missing_ba_category()
    if not part_ids:
        return
    for part_id in part_ids:
        ba_cat = await get_brickarchitect_category(part_id)
        if not ba_cat:
            continue
        levels = [lvl.strip() for lvl in ba_cat.split(" › ")]
        if len(levels) < 2:
            continue
        cat_name, sub_name = levels[0], levels[1]
        group_name = levels[2] if len(levels) >= 3 else None
        conn = get_db()
        try:
            cat_row = conn.execute(
                "SELECT id FROM categories WHERE name = ?", (cat_name,)
            ).fetchone()
            if not cat_row:
                continue
            sub_row = conn.execute(
                "SELECT id FROM subcategories WHERE category_id = ? AND name = ?",
                (cat_row["id"], sub_name),
            ).fetchone()
            if not sub_row:
                continue
            conn.execute(
                "UPDATE parts SET ba_category = ? WHERE part_id = ?",
                (ba_cat, part_id),
            )
            conn.execute("""
                INSERT INTO part_categories (part_id, category_id, subcategory_id, group_name)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(part_id) DO UPDATE SET
                    category_id    = excluded.category_id,
                    subcategory_id = excluded.subcategory_id,
                    group_name     = excluded.group_name
            """, (part_id, cat_row["id"], sub_row["id"], group_name))
            conn.commit()
        finally:
            conn.close()
        await asyncio.sleep(0.5)  # be polite to BA


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    asyncio.create_task(_refresh_missing_ba_categories())
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
