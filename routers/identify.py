"""
POST /identify
Accepts a multipart image upload, proxies it to Brickognize,
and returns the candidates HTML partial (top 3 matches).

Brickognize's item.id may be a BrickLink ID. We prefer the Rebrickable ID
since Rebrickable and BrickArchitect share IDs. Resolution order:
  1. Extract from external_sites (Rebrickable URL in Brickognize response)
  2. Query Rebrickable API with ?bricklink_id= as a fallback
"""

import os
import re
import httpx
from dotenv import load_dotenv
from fastapi import APIRouter, UploadFile, File, Request
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse

load_dotenv()

router = APIRouter()
templates = Jinja2Templates(directory="templates")

BRICKOGNIZE_URL = "https://api.brickognize.com/predict/"
REBRICKABLE_BASE = "https://rebrickable.com/api/v3/lego/parts"


async def _resolve_rebrickable_id(bricklink_id: str) -> str:
    """Query Rebrickable API to find the part number matching a BrickLink ID."""
    api_key = os.getenv("REBRICKABLE_API_KEY", "")
    if not api_key:
        return bricklink_id
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            res = await client.get(
                f"{REBRICKABLE_BASE}/",
                params={"bricklink_id": bricklink_id},
                headers={"Authorization": f"key {api_key}", "Accept": "application/json"},
            )
        if res.status_code != 200:
            return bricklink_id
        data = res.json()
        results = data.get("results", [])
        if results:
            return results[0].get("part_num", bricklink_id)
    except Exception:
        pass
    return bricklink_id


def _error(request: Request, message: str) -> HTMLResponse:
    return templates.TemplateResponse(
        "partials/_error.html",
        {"request": request, "message": message},
    )


@router.post("/identify", response_class=HTMLResponse)
async def identify(request: Request, image: UploadFile = File(...)):
    if not image or not image.filename:
        return _error(request, "No image provided — please select a photo.")

    image_data = await image.read()

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(
                BRICKOGNIZE_URL,
                headers={"accept": "application/json"},
                files={"query_image": (image.filename, image_data, image.content_type)},
            )
    except httpx.RequestError as exc:
        return _error(request, f"Could not reach Brickognize — check your connection. ({exc})")

    if response.status_code != 200:
        return _error(request, f"Brickognize returned an error ({response.status_code}). Try again.")

    data = response.json()
    raw_items = data.get("items", [])[:3]

    if not raw_items:
        return _error(request, "No matches found — try a clearer photo with better lighting.")

    import asyncio

    async def _resolve_item(item: dict) -> dict:
        part_id = item.get("id", "")
        # 1. Try external_sites first (no extra API call)
        for site in item.get("external_sites", []):
            if "rebrickable.com" in site.get("url", ""):
                m = re.search(r"/parts/([^/]+)/?", site["url"])
                if m:
                    return {**item, "id": m.group(1)}
        # 2. Fall back to Rebrickable API lookup by BrickLink ID
        resolved = await _resolve_rebrickable_id(part_id)
        return {**item, "id": resolved}

    items = await asyncio.gather(*[_resolve_item(i) for i in raw_items])

    return templates.TemplateResponse("partials/_candidates.html", {
        "request": request,
        "items":   items,
    })
