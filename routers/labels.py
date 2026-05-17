"""
POST /part/{part_id}/print-label
Downloads the .lbx label from BrickArchitect, patches it for the user's
24mm (1") PT-P710BT tape, saves to ~/Downloads, then auto-prints via
print_label.applescript.

Patch summary:
  - Retarget printer: PT-1230PC (ID 22832) → PT-P710BT (ID 30256)
  - Retarget tape:    12mm/format 259       → 24mm/format 261
  - Scale image height and font to suit the storage type's drawer width
"""

import io
import re
import subprocess
import zipfile
from pathlib import Path
from typing import NamedTuple, Optional
from xml.etree import ElementTree as ET

import httpx
from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

router = APIRouter()
templates = Jinja2Templates(directory="templates")

BA_LABEL_URL = "https://brickarchitect.com/label/{part_id}.lbx"
PRINT_SCRIPT = Path(__file__).parent.parent / "print_label.applescript"

# 24mm tape target dimensions (PT-P710BT, format 261)
# In landscape orientation marginLeft/Right are the cross-tape margins.
TAPE_24MM_WIDTH  = 68.0    # pt
TAPE_24MM_MARGIN = 8.4     # pt  cross-tape margin (matches native 24mm labels)
CONTENT_H        = TAPE_24MM_WIDTH - 2 * TAPE_24MM_MARGIN  # 51.2pt usable height

IMG_X          = 5.6    # left margin along tape
IMG_GAP        = 4.0    # gap between image right edge and text left edge
END_MARGIN     = 4.0    # right-end margin before tape edge
DEFAULT_TEXT_W = 200.0  # pt — text block width when unconstrained
FONT_PT        = 14     # base font size for unconstrained / full-size labels
MIN_FONT_PT    = 9      # never go below this


class _LabelSpec(NamedTuple):
    """Dimensional spec for a print size option."""
    max_len_pt: Optional[float]  # max label length along tape; None = unconstrained
    img_scale: float             # image height as fraction of CONTENT_H (1.0 = full tape)


# Small = 2" (Akro-Mils 64-drawer, bead boxes)
# Medium = 4.5" (Akro-Mils 24-drawer)
# Large = unconstrained (shoe boxes, overflow, etc.)
_SIZE_SPECS: dict[str, _LabelSpec] = {
    "small":  _LabelSpec(max_len_pt=144.0, img_scale=0.55),
    "medium": _LabelSpec(max_len_pt=324.0, img_scale=1.0),
    "large":  _LabelSpec(max_len_pt=None,  img_scale=1.0),
}
_DEFAULT_SPEC = _SIZE_SPECS["large"]


def _pt(v: float) -> str:
    """Format a float as a pt string, dropping unnecessary decimals."""
    return f"{v:g}pt"


def _parse_pt(s: str) -> float:
    """Parse '12.3pt' → 12.3."""
    return float(s.replace("pt", ""))


def _patch_label_xml(xml_bytes: bytes, spec: _LabelSpec = _DEFAULT_SPEC) -> bytes:
    """Rebuild label.xml dimensions for 24mm tape, scaling image and font to spec."""
    xml = xml_bytes.decode("utf-8")

    # 1. Retarget printer, tape format, width, and cross-tape margins
    xml = xml.replace(
        'printerID="22832" printerName="Brother PT-1230PC"',
        'printerID="30256" printerName="Brother PT-P710BT"',
    )
    xml = xml.replace('format="259"', 'format="261"')
    xml = xml.replace('width="33.6pt"', f'width="{_pt(TAPE_24MM_WIDTH)}"')
    xml = xml.replace('marginLeft="4pt"',  f'marginLeft="{_pt(TAPE_24MM_MARGIN)}"')
    xml = xml.replace('marginRight="4pt"', f'marginRight="{_pt(TAPE_24MM_MARGIN)}"')

    # 2. Scale and position the image object
    img_m = re.search(
        r'<image:image>.*?<pt:objectStyle\s[^>]*x="([^"]+)"\s+y="([^"]+)"\s+width="([^"]+)"\s+height="([^"]+)"',
        xml, re.DOTALL,
    )
    if img_m:
        src_img_w = _parse_pt(img_m.group(3))
        src_img_h = _parse_pt(img_m.group(4))

        # Scale image height to spec fraction; centre vertically on the tape
        img_h_24 = round(CONTENT_H * spec.img_scale, 3)
        img_w_24 = round(src_img_w * (img_h_24 / src_img_h), 3)
        img_y    = round(TAPE_24MM_MARGIN + (CONTENT_H - img_h_24) / 2, 3)

        old_img_dims = f'x="{img_m.group(1)}" y="{img_m.group(2)}" width="{img_m.group(3)}" height="{img_m.group(4)}"'
        new_img_dims = f'x="{_pt(IMG_X)}" y="{_pt(img_y)}" width="{_pt(img_w_24)}" height="{_pt(img_h_24)}"'
        xml = xml.replace(old_img_dims, new_img_dims)
        xml = re.sub(
            r'orgPos x="[^"]+" y="[^"]+" width="[^"]+" height="[^"]+"',
            f'orgPos x="{_pt(IMG_X)}" y="{_pt(img_y)}" width="{_pt(img_w_24)}" height="{_pt(img_h_24)}"',
            xml,
        )
        text_x = IMG_X + img_w_24 + IMG_GAP
    else:
        text_x = 60.0  # fallback if no image found

    # 3. Calculate text block width and scale font proportionally
    if spec.max_len_pt is not None:
        text_w = max(40.0, spec.max_len_pt - text_x - END_MARGIN)
    else:
        text_w = DEFAULT_TEXT_W

    font_pt  = max(MIN_FONT_PT, round(FONT_PT * min(1.0, text_w / DEFAULT_TEXT_W)))
    font_org = round(font_pt * 3.6, 1)

    txt_m = re.search(
        r'<text:text>.*?<pt:objectStyle\s[^>]*x="([^"]+)"\s+y="([^"]+)"\s+width="([^"]+)"\s+height="([^"]+)"',
        xml, re.DOTALL,
    )
    if txt_m:
        old_txt_dims = f'x="{txt_m.group(1)}" y="{txt_m.group(2)}" width="{txt_m.group(3)}" height="{txt_m.group(4)}"'
        new_txt_dims = f'x="{_pt(text_x)}" y="{_pt(TAPE_24MM_MARGIN)}" width="{_pt(text_w)}" height="{_pt(CONTENT_H)}"'
        xml = xml.replace(old_txt_dims, new_txt_dims)

    # 4. Background: expand to full content area
    xml = re.sub(r'(backGround\b[^/]*)y="[^"]+"',      lambda m: m.group(1) + f'y="{_pt(TAPE_24MM_MARGIN)}"', xml)
    xml = re.sub(r'(backGround\b[^/]*)height="[^"]+"', lambda m: m.group(1) + f'height="{_pt(CONTENT_H)}"',   xml)

    # 5. Scale font sizes
    xml = xml.replace('size="8pt"',       f'size="{_pt(font_pt)}"')
    xml = xml.replace('orgSize="28.8pt"', f'orgSize="{_pt(font_org)}"')

    return xml.encode("utf-8")


def _patch_lbx(data: bytes, spec: _LabelSpec = _DEFAULT_SPEC) -> bytes:
    """Repack the .lbx ZIP with a patched label.xml."""
    src, dst = io.BytesIO(data), io.BytesIO()
    with zipfile.ZipFile(src, "r") as zin, \
         zipfile.ZipFile(dst, "w", zipfile.ZIP_DEFLATED) as zout:
        for item in zin.infolist():
            content = zin.read(item.filename)
            if item.filename == "label.xml":
                content = _patch_label_xml(content, spec)
            zout.writestr(item, content)
    return dst.getvalue()


@router.post("/part/{part_id}/print-label", response_class=HTMLResponse)
async def print_label(
    request: Request,
    part_id: str,
    size: str = Form("large"),
):
    spec = _SIZE_SPECS.get(size, _DEFAULT_SPEC)

    url = BA_LABEL_URL.format(part_id=part_id)
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            res = await client.get(url)
    except httpx.RequestError as exc:
        return _toast(request, f"Could not reach BrickArchitect. ({exc})", error=True)

    if res.status_code != 200:
        return _toast(request, f"No label available for part {part_id}.", error=True)

    patched = _patch_lbx(res.content, spec)
    downloads = Path.home() / "Downloads"
    downloads.mkdir(exist_ok=True)
    label_path = downloads / f"brickfinder-{part_id}.lbx"
    label_path.write_bytes(patched)

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

    return _toast(request, "Label sent to printer ✓")


def _toast(request: Request, message: str, error: bool = False) -> HTMLResponse:
    return templates.TemplateResponse(
        "partials/_toast.html",
        {"request": request, "message": message, "error": error},
    )
