"""
Camberbrick Green — FastAPI application entry point.
"""

import asyncio
from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from contextlib import asynccontextmanager

from database import init_db, get_all_part_ids, get_db
from routers import identify, parts, collection, lookup, storage, library, labels
from routers.parts import get_brickarchitect_info


async def _backfill_ba_info():
    """Background task: fetch BA name + category for all parts, updating both."""
    await asyncio.sleep(2)  # let the server finish starting
    part_ids = get_all_part_ids()
    for part_id in part_ids:
        ba_name, ba_cat = await get_brickarchitect_info(part_id)
        if not ba_name and not ba_cat:
            await asyncio.sleep(0.5)
            continue
        levels = [lvl.strip() for lvl in ba_cat.split(" › ")] if ba_cat else []
        conn = get_db()
        try:
            if ba_name:
                conn.execute("UPDATE parts SET name = ? WHERE part_id = ?", (ba_name, part_id))
            if ba_cat:
                conn.execute("UPDATE parts SET ba_category = ? WHERE part_id = ?", (ba_cat, part_id))
            if len(levels) >= 2:
                cat_name, sub_name = levels[0], levels[1]
                group_name = levels[2] if len(levels) >= 3 else None
                cat_row = conn.execute(
                    "SELECT id FROM categories WHERE name = ?", (cat_name,)
                ).fetchone()
                if cat_row:
                    sub_row = conn.execute(
                        "SELECT id FROM subcategories WHERE category_id = ? AND name = ?",
                        (cat_row["id"], sub_name),
                    ).fetchone()
                    if sub_row:
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
    asyncio.create_task(_backfill_ba_info())
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
app.include_router(labels.router)


# ── Page routes ────────────────────────────────────────────────────────────────
@app.get("/")
async def scan(request: Request):
    return templates.TemplateResponse("scan.html", {"request": request})



@app.get("/health")
async def health():
    return {"status": "ok", "app": "Camberbrick Green"}
