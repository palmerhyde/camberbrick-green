"""
GET /part/{part_id}
Full-page part detail: merges local collection data with Rebrickable + BrickArchitect.
"""

import asyncio
import os
import re
import httpx
from fastapi import APIRouter, Request
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse
from dotenv import load_dotenv

from database import get_db
from routers.collection import _get_part_with_location

load_dotenv()

router = APIRouter()
templates = Jinja2Templates(directory="templates")

REBRICKABLE_BASE = "https://rebrickable.com/api/v3/lego/parts"


async def get_brickarchitect_category(part_id: str) -> str:
    """Scrape the category breadcrumb from BrickArchitect."""
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            res = await client.get(f"https://brickarchitect.com/parts/{part_id}")
        if res.status_code != 200:
            return ""
        html = res.text
        nav_match = re.search(r'<div class="chapternav">([\s\S]*?)</div>', html, re.IGNORECASE)
        if not nav_match:
            return ""
        anchors = re.findall(r'<a[^>]*>([^<]+)</a>', nav_match.group(1))
        if len(anchors) <= 1:
            return ""
        return " › ".join(a.strip() for a in anchors[1:])
    except Exception:
        return ""


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
        return {
            "name":    data.get("name", ""),
            "img_url": data.get("part_img_url", ""),
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

    rb, ba_cat = await asyncio.gather(
        _fetch_rebrickable(part_id),
        get_brickarchitect_category(part_id),
    )

    name    = (part or {}).get("name") or rb.get("name") or part_id
    img_url = (part or {}).get("img_url") or rb.get("img_url") or ""
    # Use stored full BA category; fall back to live-fetched for first view
    category = (part or {}).get("ba_category") or ba_cat

    # Cache img_url, full BA category string, and category assignment into DB
    if img_url or ba_cat:
        try:
            conn2 = get_db()
            if img_url and not (part or {}).get("img_url"):
                conn2.execute(
                    "UPDATE parts SET img_url = ? WHERE part_id = ?",
                    (img_url, part_id)
                )
            if ba_cat and not (part or {}).get("ba_category"):
                conn2.execute(
                    "UPDATE parts SET ba_category = ? WHERE part_id = ?",
                    (ba_cat, part_id)
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
        except Exception:
            pass

    category_parts = [p.strip() for p in category.split(" › ")] if category else []

    return templates.TemplateResponse("part_detail.html", {
        "request":        request,
        "part_id":        part_id,
        "name":           name,
        "img_url":        img_url,
        "category":       category,
        "category_parts": category_parts,
        "part":           part,
        "in_collection":  part is not None,
        "storage_types":  storage_types,
    })
