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
import time
import zipfile
from pathlib import Path
from typing import NamedTuple, Optional
from xml.etree import ElementTree as ET

from PIL import Image

import httpx
from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from database import get_db
from routers.parts import get_brickarchitect_info

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


_PROP_XML = (
    '<?xml version="1.0" encoding="UTF-8"?>'
    '<meta:properties xmlns:meta="http://schemas.brother.info/ptouch/2007/lbx/meta"'
    ' xmlns:dc="http://purl.org/dc/elements/1.1/"'
    ' xmlns:dcterms="http://purl.org/dc/terms/">'
    '<meta:appName>P-touch Editor</meta:appName>'
    '<dc:title></dc:title><dc:subject></dc:subject>'
    '<dc:creator>brickfinder</dc:creator>'
    '<meta:keyword></meta:keyword><dc:description></dc:description>'
    '<meta:template></meta:template>'
    '<dcterms:created>2024-01-01T00:00:00Z</dcterms:created>'
    '<dcterms:modified>2024-01-01T00:00:00Z</dcterms:modified>'
    '<meta:lastPrinted></meta:lastPrinted>'
    '<meta:modifiedBy>brickfinder</meta:modifiedBy>'
    '<meta:revision>1</meta:revision><meta:editTime>0</meta:editTime>'
    '<meta:numPages>1</meta:numPages><meta:numWords>0</meta:numWords>'
    '<meta:numChars>0</meta:numChars><meta:security>0</meta:security>'
    '</meta:properties>'
)

# label.xml template for a 12mm BA-style label (same baseline as BA originals;
# _patch_label_xml will scale it to 24mm tape).
# {img_w}/{img_h} are the image object dimensions in pt, derived from the actual
# image aspect ratio so _patch_label_xml preserves it when scaling to 24mm.
_LABEL_XML_TMPL = """\
<?xml version="1.0" encoding="UTF-8"?><pt:document xmlns:pt="http://schemas.brother.info/ptouch/2007/lbx/main" xmlns:style="http://schemas.brother.info/ptouch/2007/lbx/style" xmlns:text="http://schemas.brother.info/ptouch/2007/lbx/text" xmlns:draw="http://schemas.brother.info/ptouch/2007/lbx/draw" xmlns:image="http://schemas.brother.info/ptouch/2007/lbx/image" xmlns:barcode="http://schemas.brother.info/ptouch/2007/lbx/barcode" xmlns:database="http://schemas.brother.info/ptouch/2007/lbx/database" xmlns:table="http://schemas.brother.info/ptouch/2007/lbx/table" xmlns:cable="http://schemas.brother.info/ptouch/2007/lbx/cable" version="1.7" generator="P-touch Editor 5.4.014 Windows"><pt:body currentSheet="Sheet 1" direction="LTR"><style:sheet name="Sheet 1"><style:paper media="0" width="33.6pt" height="850pt" marginLeft="4pt" marginTop="5.6pt" marginRight="4pt" marginBottom="5.6pt" orientation="landscape" autoLength="true" monochromeDisplay="true" printColorDisplay="false" printColorsID="0" paperColor="#FFFFFF" paperInk="#000000" split="1" format="259" backgroundTheme="0" printerID="22832" printerName="Brother PT-1230PC"/><style:cutLine regularCut="0pt" freeCut=""/><style:backGround x="5.6pt" y="4pt" width="67pt" height="25.6pt" brushStyle="NULL" brushId="0" userPattern="NONE" userPatternId="0" color="#000000" printColorNumber="1" backColor="#FFFFFF" backPrintColorNumber="0"/><pt:objects><text:text><pt:objectStyle x="44.971pt" y="4pt" width="200pt" height="25.6pt" backColor="#FFFFFF" backPrintColorNumber="0" ropMode="COPYPEN" angle="0" anchor="TOPLEFT" flip="NONE"><pt:pen style="NULL" widthX="0.5pt" widthY="0.5pt" color="#000000" printColorNumber="1"/><pt:brush style="NULL" color="#000000" printColorNumber="1" id="0"/><pt:expanded objectName="Text1" ID="0" lock="0" templateMergeTarget="LABELLIST" templateMergeType="NONE" templateMergeID="0" linkStatus="NONE" linkID="0"/></pt:objectStyle><text:ptFontInfo><text:logFont name="Arial" width="0" italic="false" weight="400" charSet="0" pitchAndFamily="34"/><text:fontExt effect="NOEFFECT" underline="0" strikeout="0" size="8pt" orgSize="28.8pt" textColor="#000000" textPrintColorNumber="1"/></text:ptFontInfo><text:textControl control="FREE" clipFrame="false" aspectNormal="true" shrink="false" autoLF="false" avoidImage="false"/><text:textAlign horizontalAlignment="JUSTIFY" verticalAlignment="CENTER" inLineAlignment="BASELINE"/><text:textStyle vertical="false" nullBlock="false" charSpace="0" lineSpace="-10" orgPoint="10pt" combinedChars="false"/><pt:data>{name}
{part_id}</pt:data><text:stringItem charLen="{name_len}"><text:ptFontInfo><text:logFont name="Arial" width="0" italic="false" weight="700" charSet="0" pitchAndFamily="34"/><text:fontExt effect="NOEFFECT" underline="0" strikeout="0" size="8pt" orgSize="28.8pt" textColor="#000000" textPrintColorNumber="1"/></text:ptFontInfo></text:stringItem><text:stringItem charLen="{id_len}"><text:ptFontInfo><text:logFont name="Arial" width="0" italic="false" weight="400" charSet="0" pitchAndFamily="34"/><text:fontExt effect="NOEFFECT" underline="0" strikeout="0" size="8pt" orgSize="28.8pt" textColor="#000000" textPrintColorNumber="1"/></text:ptFontInfo></text:stringItem></text:text><image:image><pt:objectStyle x="5.6pt" y="4pt" width="{img_w}pt" height="{img_h}pt" backColor="#FFFFFF" backPrintColorNumber="0" ropMode="COPYPEN" angle="0" anchor="TOPLEFT" flip="NONE"><pt:pen style="NULL" widthX="0.5pt" widthY="0.5pt" color="#000000" printColorNumber="1"/><pt:brush style="NULL" color="#000000" printColorNumber="1" id="0"/><pt:expanded objectName="Image1" ID="0" lock="2" templateMergeTarget="LABELLIST" templateMergeType="NONE" templateMergeID="0" linkStatus="NONE" linkID="0"/></pt:objectStyle><image:imageStyle originalName="{img_file}" alignInText="LEFT" firstMerge="true" fileName="{img_file}"><image:transparent flag="false" color="#FFFFFF"/><image:trimming flag="false" shape="RECTANGLE" trimOrgX="0pt" trimOrgY="0pt" trimOrgWidth="{img_w}pt" trimOrgHeight="{img_h}pt"/><image:orgPos x="5.6pt" y="4pt" width="{img_w}pt" height="{img_h}pt"/><image:effect effect="NONE" brightness="50" contrast="50" photoIndex="4"/><image:mono operationKind="BINARY" reverse="0" ditherKind="MESH" threshold="128" gamma="100" ditherEdge="0" rgbconvProportionRed="30" rgbconvProportionGreen="59" rgbconvProportionBlue="11" rgbconvProportionReversed="0"/></image:imageStyle></image:image></pt:objects></style:sheet></pt:body></pt:document>"""

def _img_to_png(img_bytes: bytes) -> tuple[bytes, int, int]:
    """Convert any image format to PNG. Returns (png_bytes, width_px, height_px)."""
    img = Image.open(io.BytesIO(img_bytes)).convert("RGBA")
    w, h = img.size
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue(), w, h


def _build_custom_lbx(img_bytes: bytes, name: str, part_id: str, spec: _LabelSpec, alt_id: Optional[str] = None) -> bytes:
    """Build a BA-style .lbx from scratch using the given image bytes."""
    png_bytes, px_w, px_h = _img_to_png(img_bytes)

    # Scale image to fit the 12mm baseline height (25.6pt), preserving aspect ratio.
    # _patch_label_xml will read these dimensions and scale them correctly to 24mm.
    BASE_H = 25.6
    img_h = round(BASE_H, 3)
    img_w = round(BASE_H * px_w / px_h, 3)

    display_id = f"{part_id} / {alt_id}" if alt_id else part_id
    img_file = f"{part_id}.png"

    label_xml = _LABEL_XML_TMPL.format(
        name=name,
        part_id=display_id,
        name_len=len(name) + 1,  # +1 for the \n between name and part_id
        id_len=len(display_id),
        img_w=img_w,
        img_h=img_h,
        img_file=img_file,
    )
    patched_xml = _patch_label_xml(label_xml.encode("utf-8"), spec)
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zout:
        zout.writestr("prop.xml", _PROP_XML)
        zout.writestr(img_file, png_bytes)
        zout.writestr("label.xml", patched_xml)
    return buf.getvalue()


@router.post("/part/{part_id}/print-label", response_class=HTMLResponse)
async def print_label(
    request: Request,
    part_id: str,
    size: str = Form("large"),
):
    spec = _SIZE_SPECS.get(size, _DEFAULT_SPEC)

    # Look up alt_part_id and img_url in case we need them as fallbacks
    try:
        conn = get_db()
        row = conn.execute(
            "SELECT alt_part_id, img_url, name FROM parts WHERE part_id = ?", (part_id,)
        ).fetchone()
        alt_id    = row["alt_part_id"] if row else None
        img_url   = row["img_url"]     if row else None
        part_name = row["name"]        if row else part_id
        conn.close()
    except Exception:
        alt_id = None
        img_url = None
        part_name = part_id

    # If there's an alt ID, prefer the BA name for it (e.g. "Helmet Mask. Royal Guards"
    # instead of the Brickognize name "Minifigure, Headgear Helmet SW Royal Guard")
    if alt_id:
        try:
            ba_name, _, _ = await get_brickarchitect_info(alt_id)
            if ba_name:
                part_name = ba_name
        except Exception:
            pass

    def _ba_label_missing(r: httpx.Response) -> bool:
        return r.status_code != 200 or r.content[:5] == b"ERROR"

    url = BA_LABEL_URL.format(part_id=part_id)
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            res = await client.get(url, follow_redirects=True)

            # BA returns HTTP 200 with body "ERROR: Part image not found." for missing labels
            if _ba_label_missing(res):
                # Try resolving a redirect canonical ID from the BA HTML page
                page = await client.get(
                    f"https://brickarchitect.com/parts/{part_id}",
                    follow_redirects=True,
                )
                canonical = str(page.url).rstrip("/").split("/")[-1]
                if canonical and canonical != part_id:
                    res = await client.get(
                        BA_LABEL_URL.format(part_id=canonical),
                        follow_redirects=True,
                    )

            # Still missing — try the stored alt_part_id
            if _ba_label_missing(res) and alt_id:
                res = await client.get(
                    BA_LABEL_URL.format(part_id=alt_id),
                    follow_redirects=True,
                )

    except httpx.RequestError as exc:
        return _toast(request, f"Could not reach BrickArchitect. ({exc})", error=True)

    if _ba_label_missing(res):
        # Last resort: generate a custom label from the stored part image
        if img_url:
            try:
                async with httpx.AsyncClient(timeout=15) as client:
                    img_res = await client.get(img_url, follow_redirects=True)
                if img_res.status_code == 200:
                    patched = _build_custom_lbx(img_res.content, part_name or part_id, part_id, spec, alt_id=alt_id)
                else:
                    return _toast(request, f"No label available for part {part_id}.", error=True)
            except Exception as exc:
                return _toast(request, f"Could not build custom label. ({exc})", error=True)
        else:
            return _toast(request, f"No label available for part {part_id}.", error=True)
    else:
        patched = _patch_lbx(res.content, spec)
    downloads = Path.home() / "Downloads"
    downloads.mkdir(exist_ok=True)
    label_path = downloads / f"brickfinder-{part_id}-{round(time.time())}.lbx"
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
