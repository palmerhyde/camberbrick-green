"""
POST /lookup   — check collection + optionally enrich from Rebrickable, return HTML
POST /add-part — save part to collection, return confirmation HTML
"""

import os
import re
import httpx
from fastapi import APIRouter, Form, Request
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse
from typing import Optional
from dotenv import load_dotenv

from database import get_db
from routers.collection import _get_part_with_location, _get_or_create_location
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

    # BrickArchitect category takes priority — it's the physical storage hierarchy
    return {
        **rb,
        "category": ba_cat or rb.get("rb_category", ""),
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

    return templates.TemplateResponse("partials/_not_found.html", {
        "request":  request,
        "part_id":  part_id,
        "name":     resolved_name,
        "img_url":  resolved_img,
        "category": resolved_cat,
    })


@router.post("/add-part", response_class=HTMLResponse)
async def add_part(
    request: Request,
    part_id:  str = Form(...),
    name:     str = Form(""),
    img_url:  str = Form(""),
    category: str = Form(""),
    location: str = Form(...),
    qty:      int = Form(1),
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

        loc_id = _get_or_create_location(conn, location)

        conn.execute("""
            INSERT INTO part_locations (part_id, location_id, role, qty)
            VALUES (?, ?, 'primary', ?)
            ON CONFLICT(part_id, location_id) DO UPDATE SET qty = excluded.qty
        """, (part_id, loc_id, qty))

        conn.commit()
    finally:
        conn.close()

    return templates.TemplateResponse("partials/_added.html", {
        "request":  request,
        "part_id":  part_id,
        "name":     name or part_id,
        "location": location,
    })
