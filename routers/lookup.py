"""
POST /lookup   — check collection + optionally enrich from Rebrickable, return HTML
POST /add-part — save part to collection, return confirmation HTML
"""

import os
import re
import httpx
from fastapi import APIRouter, Form, Request
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse, RedirectResponse
from typing import Optional
from dotenv import load_dotenv

from database import get_db
from routers.collection import _get_part_with_location, _get_or_create_location, _upsert_part_category
from routers.parts import get_brickarchitect_category

load_dotenv()

router = APIRouter()
templates = Jinja2Templates(directory="templates")

REBRICKABLE_BASE = "https://rebrickable.com/api/v3/lego/parts"


async def _enrich(part_id: str) -> dict:
    """Fetch name, img_url, and category from Rebrickable + BrickArchitect. Returns {} on failure."""
    import asyncio

    api_key = os.getenv("REBRICKABLE_API_KEY", "")

    async def _rebrickable():
        if not api_key or api_key == "your_key_here":
            return {}
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                res = await client.get(
                    f"{REBRICKABLE_BASE}/{part_id}/",
                    headers={"Authorization": f"key {api_key}", "Accept": "application/json"},
                )
            if res.status_code != 200:
                return {}
            data = res.json()
            cat = data.get("part_category", {})
            rb_cat = cat.get("name", "") if isinstance(cat, dict) else str(cat or "")
            return {
                "name":    data.get("name", ""),
                "img_url": data.get("part_img_url", ""),
                "rb_category": rb_cat,
            }
        except Exception:
            return {}

    rb, ba_cat = await asyncio.gather(_rebrickable(), get_brickarchitect_category(part_id))

    # BrickArchitect is the only category system — never fall back to Rebrickable
    return {
        **rb,
        "category": ba_cat,
        "brickarchitect_category": ba_cat,
    }


@router.post("/lookup", response_class=HTMLResponse)
async def lookup(
    request: Request,
    part_id: str = Form(...),
    name: Optional[str] = Form(None),
    img_url: Optional[str] = Form(None),
):
    part_id = part_id.strip()

    conn = get_db()
    try:
        part = _get_part_with_location(conn, part_id)
    finally:
        conn.close()

    # Best-effort Rebrickable enrichment (non-blocking on failure)
    rb = await _enrich(part_id)

    resolved_img = img_url or rb.get("img_url") or (part or {}).get("img_url") or ""

    if part:
        part["img_url"] = part.get("img_url") or resolved_img
        # Prefer live BrickArchitect category over whatever is stored in the DB
        if rb.get("brickarchitect_category"):
            part["category"] = rb["brickarchitect_category"]
            part["subcategory"] = None  # BA breadcrumb already contains both levels
        return templates.TemplateResponse("partials/_result.html", {
            "request": request,
            "part":    part,
            "img_url": resolved_img,
        })

    resolved_name = name or rb.get("name") or part_id
    resolved_cat  = rb.get("category", "")

    conn2 = get_db()
    try:
        storage_types = conn2.execute(
            "SELECT * FROM storage_types ORDER BY sort_order, name"
        ).fetchall()
    finally:
        conn2.close()

    return templates.TemplateResponse("partials/_not_found.html", {
        "request":      request,
        "part_id":      part_id,
        "name":         resolved_name,
        "img_url":      resolved_img,
        "category":     resolved_cat,
        "storage_types": storage_types,
    })


@router.post("/add-part", response_class=HTMLResponse)
async def add_part(
    request: Request,
    part_id:  str = Form(...),
    name:     str = Form(""),
    img_url:  str = Form(""),
    category: str = Form(""),
    location: str = Form(...),
):
    part_id  = part_id.strip()
    location = location.strip()

    conn = get_db()
    try:
        conn.execute("""
            INSERT INTO parts (part_id, name, known_owned, img_url)
            VALUES (?, ?, 1, ?)
            ON CONFLICT(part_id) DO UPDATE SET
                name       = COALESCE(excluded.name, name),
                img_url    = COALESCE(NULLIF(excluded.img_url, ''), img_url),
                updated_at = datetime('now')
        """, (part_id, name or part_id, img_url or None))

        # Find the storage_type_id for the selected location name
        st_row = conn.execute(
            "SELECT id FROM storage_types WHERE name = ?", (location,)
        ).fetchone()
        st_id = st_row["id"] if st_row else None

        # Find or create the location entry, linked to its storage type
        existing = conn.execute(
            "SELECT id FROM locations WHERE code = ?", (location,)
        ).fetchone()
        if existing:
            loc_id = existing["id"]
            if st_id:
                conn.execute(
                    "UPDATE locations SET storage_type_id = ? WHERE id = ?",
                    (st_id, loc_id),
                )
        else:
            conn.execute(
                "INSERT INTO locations (code, type, description, storage_type_id) VALUES (?, ?, ?, ?)",
                (location, "storage_type", location, st_id),
            )
            loc_id = conn.execute(
                "SELECT id FROM locations WHERE code = ?", (location,)
            ).fetchone()["id"]

        conn.execute("""
            INSERT INTO part_locations (part_id, location_id, role, qty)
            VALUES (?, ?, 'primary', 1)
            ON CONFLICT(part_id, location_id) DO UPDATE SET qty = 1
        """, (part_id, loc_id))

        _upsert_part_category(conn, part_id, category)
        conn.commit()
    finally:
        conn.close()

    return templates.TemplateResponse("partials/_added.html", {
        "request":  request,
        "part_id":  part_id,
        "name":     name or part_id,
        "location": location,
    })


def _get_storage_types(conn):
    return conn.execute(
        "SELECT * FROM storage_types ORDER BY sort_order, name"
    ).fetchall()


def _upsert_location(conn, location: str) -> int:
    """Find or create a location row for the given storage type name. Returns location id."""
    st_row = conn.execute(
        "SELECT id FROM storage_types WHERE name = ?", (location,)
    ).fetchone()
    st_id = st_row["id"] if st_row else None

    existing = conn.execute("SELECT id FROM locations WHERE code = ?", (location,)).fetchone()
    if existing:
        loc_id = existing["id"]
        if st_id:
            conn.execute(
                "UPDATE locations SET storage_type_id = ? WHERE id = ?", (st_id, loc_id)
            )
    else:
        conn.execute(
            "INSERT INTO locations (code, type, description, storage_type_id) VALUES (?, ?, ?, ?)",
            (location, "storage_type", location, st_id),
        )
        loc_id = conn.execute("SELECT id FROM locations WHERE code = ?", (location,)).fetchone()["id"]
    return loc_id


@router.get("/part/{part_id}/edit", response_class=HTMLResponse)
async def edit_part_page(request: Request, part_id: str):
    conn = get_db()
    try:
        part = _get_part_with_location(conn, part_id)
        storage_types = _get_storage_types(conn)
    finally:
        conn.close()

    if not part:
        return templates.TemplateResponse("partials/_error.html", {
            "request": request,
            "message": f"Part {part_id} not found in your collection.",
        })

    return templates.TemplateResponse("edit_part.html", {
        "request":       request,
        "part":          part,
        "storage_types": storage_types,
        "error":         "",
    })


@router.post("/part/{part_id}/edit")
async def edit_part_save(
    request: Request,
    part_id:  str,
    location: str = Form(...),
):
    conn = get_db()
    try:
        part = _get_part_with_location(conn, part_id)
        if not part:
            return templates.TemplateResponse("partials/_error.html", {
                "request": request,
                "message": f"Part {part_id} not found.",
            })

        loc_id = _upsert_location(conn, location)

        # Replace primary location
        conn.execute(
            "DELETE FROM part_locations WHERE part_id = ? AND role = 'primary'",
            (part_id,),
        )
        conn.execute(
            "INSERT INTO part_locations (part_id, location_id, role, qty) VALUES (?, ?, 'primary', 1)",
            (part_id, loc_id),
        )
        conn.execute(
            "UPDATE parts SET updated_at = datetime('now') WHERE part_id = ?",
            (part_id,),
        )
        conn.commit()
    finally:
        conn.close()

    return RedirectResponse("/library", status_code=303)
