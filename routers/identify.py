"""
POST /identify
Accepts a multipart image upload, proxies it to Brickognize,
and returns the top 3 candidate matches.
"""

import httpx
from fastapi import APIRouter, UploadFile, File, HTTPException

router = APIRouter()

BRICKOGNIZE_URL = "https://api.brickognize.com/predict/"


@router.post("/identify")
async def identify(image: UploadFile = File(...)):
    if not image:
        raise HTTPException(status_code=400, detail="No image provided")

    image_data = await image.read()

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(
                BRICKOGNIZE_URL,
                headers={"accept": "application/json"},
                files={"query_image": (image.filename, image_data, image.content_type)},
            )
    except httpx.RequestError as e:
        raise HTTPException(status_code=502, detail=f"Brickognize unreachable: {e}")

    if response.status_code != 200:
        raise HTTPException(
            status_code=502,
            detail=f"Brickognize error {response.status_code}: {response.text}",
        )

    data = response.json()
    # Return top 3 candidates so the user can confirm the right match
    items = data.get("items", [])[:3]

    if not items:
        raise HTTPException(status_code=404, detail="No matches found — try a clearer photo")

    return {"items": items}
