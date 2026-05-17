"""
GET /part/{part_id}
Fetches part details from Rebrickable (name, image, category)
and enriches with a BrickArchitect category breadcrumb.
"""

import os
import re
import httpx
from fastapi import APIRouter, HTTPException
from dotenv import load_dotenv

load_dotenv()

router = APIRouter()

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


@router.get("/part/{part_id}")
async def get_part(part_id: str):
    api_key = os.getenv("REBRICKABLE_API_KEY")
    if not api_key or api_key == "your_key_here":
        raise HTTPException(status_code=500, detail="REBRICKABLE_API_KEY not configured in .env")

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            res = await client.get(
                f"{REBRICKABLE_BASE}/{part_id}/",
                headers={"Authorization": f"key {api_key}", "Accept": "application/json"},
            )
    except httpx.RequestError as e:
        raise HTTPException(status_code=502, detail=f"Rebrickable unreachable: {e}")

    if res.status_code == 404:
        raise HTTPException(status_code=404, detail=f"Part {part_id} not found on Rebrickable")
    if res.status_code != 200:
        raise HTTPException(status_code=502, detail=f"Rebrickable error {res.status_code}")

    data = res.json()

    rebrickable_category = (
        data.get("part_category", {}).get("name", "")
        if isinstance(data.get("part_category"), dict)
        else str(data.get("part_category") or "")
    )

    brickarchitect_category = await get_brickarchitect_category(part_id)
    category = brickarchitect_category  # BrickArchitect only — never fall back to Rebrickable

    return {
        "id":                    data.get("part_num", part_id),
        "name":                  data.get("name", part_id),
        "category":              category,
        "rebrickable_category":  rebrickable_category,
        "brickarchitect_category": brickarchitect_category,
        "img_url":               data.get("part_img_url"),
        "part_url":              data.get("part_url"),
        "brickarchitect_url":    f"https://brickarchitect.com/parts/{part_id}",
    }
