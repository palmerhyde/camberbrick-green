"""
POST /categories/print-label/{slug}
Prints a 24mm shoebox label for a top-level BrickArchitect category.

Renders the category icon + name into a single composite PNG using Pillow,
then embeds it as the sole image object in a 3001.lbx-derived template.
This avoids P-touch Editor's text rendering entirely.
"""

import asyncio
import io
import re
import subprocess
import time
import zipfile
from pathlib import Path

import cairosvg
import httpx
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from PIL import Image, ImageDraw, ImageFont

router = APIRouter()
templates = Jinja2Templates(directory="templates")

PRINT_SCRIPT    = Path(__file__).parent.parent / "print_label.applescript"
BA_ICON_URL     = "https://brickarchitect.com/content/part-categories/{slug}.svg"
BA_TEMPLATE_URL = "https://brickarchitect.com/label/3001.lbx"

_ARIAL_BOLD = "/System/Library/Fonts/Supplemental/Arial Bold.ttf"

# 24mm tape constants (shared with labels.py)
_TAPE_W  = 68.0
_MARGIN  = 8.4
_CONTENT = 51.2   # usable cross-tape height
_IMG_X   = 5.6

# Render scale: pt → px (5× gives ~360 DPI quality)
_SCALE = 5
_PX_H  = round(_CONTENT * _SCALE)   # 256 px

# SVG icon aspect ratio
_SVG_ASPECT = 40.819 / 45.354       # ≈ 0.9001


def _pt(v: float) -> str:
    return f"{v:g}pt"


def _render_composite_png(svg_bytes: bytes, category_name: str) -> tuple[bytes, float]:
    """
    Returns (png_bytes, composite_width_pt).
    Composite = icon on the left, bold category name on the right,
    all at _SCALE px/pt on a white background.
    """
    # --- Icon ---
    icon_png = cairosvg.svg2png(bytestring=svg_bytes, background_color="white",
                                output_height=_PX_H)
    icon_img = Image.open(io.BytesIO(icon_png)).convert("RGBA")
    icon_w, icon_h = icon_img.size   # icon_h == _PX_H

    # --- Text ---
    gap_px        = round(4 * _SCALE)      # 4pt gap between icon and text
    right_pad_px  = round(4 * _SCALE)      # 4pt right-end margin
    font_px       = round(18 * _SCALE)     # 18pt font
    font = ImageFont.truetype(_ARIAL_BOLD, font_px)

    # Measure the text
    dummy = Image.new("RGBA", (1, 1))
    bbox  = ImageDraw.Draw(dummy).textbbox((0, 0), category_name, font=font)
    text_w = bbox[2] - bbox[0]
    text_h = bbox[3] - bbox[1]
    text_y = (icon_h - text_h) // 2 - bbox[1]   # vertically centred

    # --- Composite canvas ---
    total_w = icon_w + gap_px + text_w + right_pad_px
    canvas  = Image.new("RGBA", (total_w, _PX_H), (255, 255, 255, 255))
    canvas.paste(icon_img, (0, 0))
    draw = ImageDraw.Draw(canvas)
    draw.text((icon_w + gap_px, text_y), category_name, fill=(0, 0, 0, 255), font=font)

    buf = io.BytesIO()
    canvas.save(buf, format="PNG")

    composite_width_pt = round(total_w / _SCALE, 3)
    return buf.getvalue(), composite_width_pt


def _patch_xml(xml: str, png_filename: str,
               img_w_pt: float, img_h_pt: float) -> str:
    # 1. Tape / printer settings
    xml = xml.replace('printerID="22832" printerName="Brother PT-1230PC"',
                      'printerID="30256" printerName="Brother PT-P710BT"')
    xml = xml.replace('format="259"', 'format="261"')
    xml = xml.replace('width="33.6pt"', f'width="{_pt(_TAPE_W)}"')
    xml = xml.replace('marginLeft="4pt"',  f'marginLeft="{_pt(_MARGIN)}"')
    xml = xml.replace('marginRight="4pt"', f'marginRight="{_pt(_MARGIN)}"')

    # 2. Background cross-tape extent
    xml = re.sub(r'(backGround\b[^/]*)y="[^"]+"',
                 lambda m: m.group(1) + f'y="{_pt(_MARGIN)}"', xml)
    xml = re.sub(r'(backGround\b[^/]*)height="[^"]+"',
                 lambda m: m.group(1) + f'height="{_pt(_CONTENT)}"', xml)

    # 3. Image object: resize to composite dimensions, update filenames
    img_m = re.search(
        r'<image:image>.*?<pt:objectStyle\s[^>]*x="([^"]+)"\s+y="([^"]+)"\s+width="([^"]+)"\s+height="([^"]+)"',
        xml, re.DOTALL,
    )
    if img_m:
        old = f'x="{img_m.group(1)}" y="{img_m.group(2)}" width="{img_m.group(3)}" height="{img_m.group(4)}"'
        new = f'x="{_pt(_IMG_X)}" y="{_pt(_MARGIN)}" width="{_pt(img_w_pt)}" height="{_pt(img_h_pt)}"'
        xml = xml.replace(old, new, 1)
    xml = re.sub(
        r'orgPos x="[^"]+" y="[^"]+" width="[^"]+" height="[^"]+"',
        f'orgPos x="{_pt(_IMG_X)}" y="{_pt(_MARGIN)}" width="{_pt(img_w_pt)}" height="{_pt(img_h_pt)}"',
        xml,
    )
    # trimOrgWidth/Height define the image's natural size — must match the composite
    # or P-touch Editor clips the display area to the old (small) dimensions
    xml = re.sub(r'trimOrgWidth="[^"]+"',  f'trimOrgWidth="{_pt(img_w_pt)}"',  xml)
    xml = re.sub(r'trimOrgHeight="[^"]+"', f'trimOrgHeight="{_pt(img_h_pt)}"', xml)
    xml = re.sub(r'originalName="[^"]+"', f'originalName="{png_filename}"', xml)
    xml = re.sub(r'fileName="[^"]+"',     f'fileName="{png_filename}"',     xml)

    # 4. Remove the text object entirely — text is baked into the composite PNG
    xml = re.sub(r'<text:text>.*?</text:text>', '', xml, flags=re.DOTALL)

    return xml


def _build_lbx(category_name: str, slug: str,
               template_lbx: bytes, svg_bytes: bytes) -> bytes:
    png_filename = f"{slug}.png"
    png_bytes, img_w_pt = _render_composite_png(svg_bytes, category_name)

    src = io.BytesIO(template_lbx)
    dst = io.BytesIO()
    with zipfile.ZipFile(src, "r") as zin, \
         zipfile.ZipFile(dst, "w", zipfile.ZIP_DEFLATED) as zout:
        for item in zin.infolist():
            if item.filename.endswith(".png"):
                zout.writestr(png_filename, png_bytes)
            elif item.filename == "label.xml":
                xml = zin.read(item.filename).decode("utf-8")
                zout.writestr(item, _patch_xml(xml, png_filename,
                                               img_w_pt, _CONTENT))
            else:
                zout.writestr(item, zin.read(item.filename))
    return dst.getvalue()


@router.post("/categories/print-label/{slug}", response_class=HTMLResponse)
async def print_category_label(request: Request, slug: str):
    icon_url = BA_ICON_URL.format(slug=slug)
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            icon_res, tmpl_res = await asyncio.gather(
                client.get(icon_url),
                client.get(BA_TEMPLATE_URL),
            )
    except httpx.RequestError as exc:
        return _toast(request, f"Could not reach BrickArchitect. ({exc})", error=True)

    if icon_res.status_code != 200:
        return _toast(request, f"No icon found for '{slug}'.", error=True)
    if tmpl_res.status_code != 200:
        return _toast(request, "Could not download label template.", error=True)

    category_name = slug.upper()
    lbx_bytes = _build_lbx(category_name, slug, tmpl_res.content, icon_res.content)

    downloads = Path.home() / "Downloads"
    downloads.mkdir(exist_ok=True)
    label_path = downloads / f"brickfinder-category-{slug}-{round(time.time())}.lbx"
    label_path.write_bytes(lbx_bytes)

    try:
        result = subprocess.run(
            ["osascript", str(PRINT_SCRIPT), str(label_path)],
            capture_output=True, text=True, timeout=15,
        )
        if result.returncode != 0:
            return _toast(request, f"Print failed: {result.stderr.strip()}", error=True)
    except subprocess.TimeoutExpired:
        return _toast(request, "Print timed out — is P-Touch Editor installed?", error=True)
    finally:
        try:
            label_path.unlink()
        except OSError:
            pass

    return _toast(request, f"{category_name} label sent to printer ✓")


def _toast(request: Request, message: str, error: bool = False) -> HTMLResponse:
    return templates.TemplateResponse(
        "partials/_toast.html",
        {"request": request, "message": message, "error": error},
    )
