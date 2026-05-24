"""
GET /part/{part_id}
Full-page part detail: merges local collection data with Rebrickable + BrickArchitect.
"""

import asyncio
import os
import re
import httpx
from fastapi import APIRouter, Form, Request
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse
from dotenv import load_dotenv

from database import get_db
from routers.collection import _get_part_with_location

load_dotenv()

router = APIRouter()
templates = Jinja2Templates(directory="templates")

REBRICKABLE_BASE = "https://rebrickable.com/api/v3/lego/parts"


async def get_brickarchitect_info(part_id: str) -> tuple[str, str]:
    """Scrape name and category breadcrumb from BrickArchitect. Returns (name, category)."""
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            res = await client.get(f"https://brickarchitect.com/parts/{part_id}",
                                   follow_redirects=True)
        if res.status_code != 200:
            return "", ""
        html = res.text
        # Name: first <h1> — strip the "(Part XXXXXX)" span
        name = ""
        h1_match = re.search(r'<h1>([^<]+)', html)
        if h1_match:
            name = h1_match.group(1).strip().rstrip(",").strip()
        # Category: breadcrumb nav, skip the first "home" anchor
        nav_match = re.search(r'<div class="chapternav">([\s\S]*?)</div>', html, re.IGNORECASE)
        category = ""
        if nav_match:
            anchors = re.findall(r'<a[^>]*>([^<]+)</a>', nav_match.group(1))
            if len(anchors) > 1:
                category = " › ".join(a.strip() for a in anchors[1:])
        return name, category
    except Exception:
        return "", ""


async def get_brickarchitect_category(part_id: str) -> str:
    """Scrape the category breadcrumb from BrickArchitect."""
    _, category = await get_brickarchitect_info(part_id)
    return category


async def _fetch_rebrickable(part_id: str) -> dict:
    api_key = os.getenv("REBRICKABLE_API_KEY", "")
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
            "name":        data.get("name", ""),
            "img_url":     data.get("part_img_url", ""),
            "rb_category": rb_cat,
        }
    except Exception:
        return {}


@router.get("/part/{part_id}", response_class=HTMLResponse)
async def part_detail(request: Request, part_id: str):
    conn = get_db()
    try:
        part = _get_part_with_location(conn, part_id)
        storage_types = conn.execute(
            "SELECT * FROM storage_types ORDER BY sort_order, name"
        ).fetchall()
    finally:
        conn.close()

    cached_name   = (part or {}).get("name")
    cached_img    = (part or {}).get("img_url")
    cached_cat    = (part or {}).get("ba_category")
    cached_rb_cat = (part or {}).get("rb_category")  # None = never tried; "" = tried, not found
    alt_part_id   = (part or {}).get("alt_part_id")

    # Treat name == part_id as "no useful name" — raw ID was stored as placeholder
    if cached_name == part_id:
        cached_name = None

    # Decide which external calls are needed.
    # cached_rb_cat is not None (including "") means Rebrickable was already tried.
    need_rb = cached_rb_cat is None
    # Need BA if: no name yet, OR no category AND haven't completed an enrichment cycle yet
    need_ba = not cached_name or (not cached_cat and cached_rb_cat is None)
    called_rb = False

    if not need_rb and not need_ba:
        rb, ba_name, ba_cat = {}, "", ""
    elif need_rb and need_ba:
        rb, (ba_name, ba_cat) = await asyncio.gather(
            _fetch_rebrickable(part_id),
            get_brickarchitect_info(part_id),
        )
        called_rb = True
    elif need_rb:
        rb, ba_name, ba_cat = await _fetch_rebrickable(part_id), "", ""
        called_rb = True
    else:
        rb, ba_name, ba_cat = {}, *await get_brickarchitect_info(part_id)

    # If primary BA lookup found nothing and we have an alt ID, try that
    if not ba_cat and not cached_cat and alt_part_id:
        _, ba_cat = await get_brickarchitect_info(alt_part_id)

    # Prefer BA name (user-friendly) → stored name → Rebrickable name
    name        = cached_name or ba_name or rb.get("name") or part_id
    img_url     = cached_img  or rb.get("img_url") or ""
    category    = cached_cat  or ba_cat
    rb_category = cached_rb_cat if cached_rb_cat is not None else rb.get("rb_category", "")

    # Cache img_url, BA name, RB category, full BA category string, and category assignment into DB
    if called_rb or img_url or ba_name or ba_cat:
        try:
            conn2 = get_db()
            if img_url and not (part or {}).get("img_url"):
                conn2.execute(
                    "UPDATE parts SET img_url = ? WHERE part_id = ?",
                    (img_url, part_id)
                )
            best_name = ba_name or rb.get("name")
            if best_name and not cached_name:
                conn2.execute(
                    "UPDATE parts SET name = ? WHERE part_id = ?",
                    (best_name, part_id)
                )
            if ba_cat and not (part or {}).get("ba_category"):
                conn2.execute(
                    "UPDATE parts SET ba_category = ? WHERE part_id = ?",
                    (ba_cat, part_id)
                )
            if called_rb and cached_rb_cat is None:
                # Always store result (even "" for not-found) so we don't retry
                conn2.execute(
                    "UPDATE parts SET rb_category = ? WHERE part_id = ?",
                    (rb.get("rb_category", ""), part_id)
                )
            # Save BA category → subcategory assignment (levels 1 and 2 of breadcrumb)
            if ba_cat:
                # breadcrumb: "Basic › Brick › 2× Brick" — store all 3 levels
                levels = [p.strip() for p in ba_cat.split(" › ")]
                if len(levels) >= 2:
                    cat_name, sub_name = levels[0], levels[1]
                    group_name = levels[2] if len(levels) >= 3 else None
                    cat_row = conn2.execute(
                        "SELECT id FROM categories WHERE name = ?", (cat_name,)
                    ).fetchone()
                    if cat_row:
                        sub_row = conn2.execute(
                            "SELECT id FROM subcategories WHERE category_id = ? AND name = ?",
                            (cat_row["id"], sub_name)
                        ).fetchone()
                        if sub_row:
                            conn2.execute("""
                                INSERT INTO part_categories (part_id, category_id, subcategory_id, group_name)
                                VALUES (?, ?, ?, ?)
                                ON CONFLICT(part_id) DO UPDATE SET
                                    category_id    = excluded.category_id,
                                    subcategory_id = excluded.subcategory_id,
                                    group_name     = excluded.group_name
                            """, (part_id, cat_row["id"], sub_row["id"], group_name))
            conn2.commit()
            conn2.close()
        except Exception as e:
            print(f"[parts] cache write error for {part_id}: {e}")

    category_parts = [p.strip() for p in category.split(" › ")] if category else []
    category_slugs = [re.sub(r"[^a-z0-9]+", "-", p.lower()).strip("-") for p in category_parts]
    is_uncategorised = not bool(category)

    return templates.TemplateResponse("part_detail.html", {
        "request":          request,
        "part_id":          part_id,
        "name":             name,
        "img_url":          img_url,
        "category":         category,
        "category_parts":   category_parts,
        "category_slugs":   category_slugs,
        "part":             part,
        "in_collection":    part is not None and part.get("location") is not None,
        "storage_types":    storage_types,
        "is_uncategorised": is_uncategorised,
        "rb_category":      rb_category,
        "alt_part_id":      alt_part_id,
    })


@router.post("/part/{part_id}/set-alt-id", response_class=HTMLResponse)
async def set_alt_part_id(request: Request, part_id: str, alt_id: str = Form("")):
    alt_id = alt_id.strip() or None
    conn = get_db()
    try:
        conn.execute("UPDATE parts SET alt_part_id = ? WHERE part_id = ?", (alt_id, part_id))
        conn.commit()
    finally:
        conn.close()
    return templates.TemplateResponse("partials/_alt_part_id.html", {
        "request":     request,
        "part_id":     part_id,
        "alt_part_id": alt_id,
        "x_prefix":    part_id.lower().startswith("x"),
    })
