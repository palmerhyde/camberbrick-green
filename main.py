"""
Camberbrick Green — FastAPI application entry point.
"""

import asyncio
import random
from datetime import date, datetime, timezone
from fastapi import FastAPI, Request
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from contextlib import asynccontextmanager

from database import init_db, get_all_part_ids, get_db
from routers import identify, parts, collection, lookup, storage, library, labels, minifigures, category_labels
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
app.include_router(minifigures.router)
app.include_router(category_labels.router)


# ── Page routes ────────────────────────────────────────────────────────────────
@app.get("/")
async def scan(request: Request):
    conn = get_db()
    try:
        parts_count = conn.execute("""
            SELECT COUNT(DISTINCT p.part_id) FROM parts p
            JOIN part_locations pl ON pl.part_id = p.part_id
            WHERE p.item_type = 'part' OR p.item_type IS NULL
        """).fetchone()[0]
        minifig_count = conn.execute("""
            SELECT COUNT(DISTINCT p.part_id) FROM parts p
            JOIN part_locations pl ON pl.part_id = p.part_id
            WHERE p.item_type = 'minifig'
        """).fetchone()[0]
        locations_count = conn.execute(
            "SELECT COUNT(*) FROM storage_types"
        ).fetchone()[0]

        # Featured minifigure: most recently added if within 7 days,
        # otherwise a daily spotlight (changes each day, stable within a day)
        featured = None
        featured_label = None
        all_mf = conn.execute("""
            SELECT p.part_id, p.name, p.img_url, p.ba_category, p.updated_at
            FROM parts p
            JOIN part_locations pl ON pl.part_id = p.part_id
            WHERE p.item_type = 'minifig'
            ORDER BY p.updated_at DESC
        """).fetchall()
        if all_mf:
            latest = all_mf[0]
            try:
                added = datetime.fromisoformat(latest["updated_at"])
                days_ago = (datetime.now() - added).days
            except Exception:
                days_ago = 999
            if days_ago < 7:
                featured = latest
                featured_label = "Latest Minifig"
            else:
                rng = random.Random(date.today().toordinal())
                featured = rng.choice(all_mf)
                featured_label = "Today's spotlight"

        latest_part = None
        latest_part_label = None
        all_parts = conn.execute("""
            SELECT p.part_id, p.name, p.img_url, p.ba_category, p.updated_at
            FROM parts p
            JOIN part_locations pl ON pl.part_id = p.part_id
            WHERE p.item_type = 'part' OR p.item_type IS NULL
            ORDER BY p.updated_at DESC
        """).fetchall()
        if all_parts:
            newest_part = all_parts[0]
            try:
                added = datetime.fromisoformat(newest_part["updated_at"])
                days_ago = (datetime.now() - added).days
            except Exception:
                days_ago = 999
            if days_ago < 7:
                latest_part = newest_part
                latest_part_label = "Latest Part"
            else:
                rng = random.Random(date.today().toordinal() + 1)
                latest_part = rng.choice(all_parts)
                latest_part_label = "Today's spotlight"
    finally:
        conn.close()

    return templates.TemplateResponse("scan.html", {
        "request":         request,
        "parts_count":     parts_count,
        "minifig_count":   minifig_count,
        "locations_count": locations_count,
        "featured":        featured,
        "featured_label":  featured_label,
        "latest_part":       latest_part,
        "latest_part_label": latest_part_label,
    })



@app.get("/library")
async def library_redirect():
    return RedirectResponse("/parts", status_code=301)


@app.get("/library/{rest:path}")
async def library_path_redirect(rest: str):
    return RedirectResponse(f"/parts/{rest}", status_code=301)


@app.get("/health")
async def health():
    return {"status": "ok", "app": "Camberbrick Green"}
