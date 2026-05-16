"""
POST /identify
Accepts a multipart image upload, proxies it to Brickognize,
and returns the candidates HTML partial (top 3 matches).
"""

import httpx
from fastapi import APIRouter, UploadFile, File, Request
from fastapi.templating import Jinja2Templates
from fastapi.responses import HTMLResponse

router = APIRouter()
templates = Jinja2Templates(directory="templates")

BRICKOGNIZE_URL = "https://api.brickognize.com/predict/"


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
    items = data.get("items", [])[:3]

    if not items:
        return _error(request, "No matches found — try a clearer photo with better lighting.")

    return templates.TemplateResponse("partials/_candidates.html", {
        "request": request,
        "items":   items,
    })
