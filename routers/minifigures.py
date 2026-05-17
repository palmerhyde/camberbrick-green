"""
Minifigure collection routes.

GET /minifigures              — browse all minifigures grouped by theme
GET /minifigure/{part_id}     — detail page for a single minifigure
POST /minifigure/{part_id}/set-location — inline location update (HTMX)
"""

from fastapi import APIRouter, Form, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from database import get_db
from routers.collection import _get_part_with_location
from routers.lookup import _get_storage_types, _upsert_location

router = APIRouter()
templates = Jinja2Templates(directory="templates")

# Map Brickognize category strings / common ID prefixes to friendly theme names
_THEME_ALIASES = {
    "harry potter":            "Harry Potter",
    "star wars":               "Star Wars",
    "collectible minifigures": "Collectible Minifigures",
    "ninjago":                 "Ninjago",
    "city":                    "City",
    "castle":                  "Castle",
    "pirates":                 "Pirates",
    "super heroes":            "Super Heroes",
    "marvel":                  "Marvel Super Heroes",
    "dc":                      "DC Super Heroes",
    "lord of the rings":       "Lord of the Rings",
    "the hobbit":              "The Hobbit",
    "the lego movie":          "The LEGO Movie",
    "jurassic world":          "Jurassic World",
    "minecraft":               "Minecraft",
    "friends":                 "Friends",
    "elves":                   "Elves",
    "ideas":                   "Ideas",
}

_ID_PREFIX_THEMES = {
    "hp":   "Harry Potter",
    "sw":   "Star Wars",
    "col":  "Collectible Minifigures",
    "njo":  "Ninjago",
    "cty":  "City",
    "cas":  "Castle",
    "pi":   "Pirates",
    "sh":   "Super Heroes",
    "lor":  "Lord of the Rings",
    "tlm":  "The LEGO Movie",
    "jw":   "Jurassic World",
    "min":  "Minecraft",
    "frnd": "Friends",
    "elf":  "Elves",
    "idea": "Ideas",
    "bat":  "Batman",
    "dp":   "Disney Princess",
    "hol":  "Holiday",
}


def _theme(part_id: str, ba_category) -> str:
    """Derive a friendly theme name from the category or ID prefix."""
    if ba_category:
        key = ba_category.strip().lower()
        if key in _THEME_ALIASES:
            return _THEME_ALIASES[key]
        # Return as-is if it looks like a real theme name (capitalised)
        return ba_category.strip()
    # Fall back to ID prefix matching
    lower = part_id.lower()
    for prefix, theme in _ID_PREFIX_THEMES.items():
        if lower.startswith(prefix) and len(lower) > len(prefix) and lower[len(prefix)].isdigit():
            return theme
    return "Other"


@router.get("/minifigures", response_class=HTMLResponse)
async def minifigures_index(request: Request):
    conn = get_db()
    try:
        rows = conn.execute("""
            SELECT
                p.part_id, p.name, p.img_url, p.ba_category,
                COALESCE(st.code, l.code) AS storage_code,
                st.name AS storage_name
            FROM parts p
            LEFT JOIN part_locations pl ON p.part_id = pl.part_id AND pl.role = 'primary'
            LEFT JOIN locations l       ON pl.location_id = l.id
            LEFT JOIN storage_types st  ON l.storage_type_id = st.id
            WHERE p.item_type = 'minifig'
            ORDER BY p.ba_category, p.name
        """).fetchall()
    finally:
        conn.close()

    # Group by theme
    groups: dict[str, list] = {}
    for row in rows:
        theme = _theme(row["part_id"], row["ba_category"])
        groups.setdefault(theme, []).append(dict(row))

    # Sort themes alphabetically, "Other" last
    sorted_themes = sorted(groups.keys(), key=lambda t: (t == "Other", t))
    grouped = [{"theme": t, "figures": groups[t]} for t in sorted_themes]

    return templates.TemplateResponse("minifigures.html", {
        "request": request,
        "grouped": grouped,
        "total":   sum(len(g["figures"]) for g in grouped),
    })


@router.get("/minifigure/{part_id}", response_class=HTMLResponse)
async def minifigure_detail(request: Request, part_id: str):
    conn = get_db()
    try:
        part = _get_part_with_location(conn, part_id)
        storage_types = _get_storage_types(conn)
    finally:
        conn.close()

    if not part:
        # Part scanned but not yet in collection — show add prompt
        return templates.TemplateResponse("minifigure_detail.html", {
            "request":       request,
            "part_id":       part_id,
            "name":          part_id,
            "theme":         _theme(part_id, None),
            "img_url":       "",
            "part":          None,
            "in_collection": False,
            "storage_types": storage_types,
        })

    theme   = _theme(part_id, part["ba_category"])
    img_url = part["img_url"] or ""
    name    = part["name"] or part_id

    return templates.TemplateResponse("minifigure_detail.html", {
        "request":       request,
        "part_id":       part_id,
        "name":          name,
        "theme":         theme,
        "img_url":       img_url,
        "part":          part,
        "in_collection": part.get("location") is not None,
        "storage_types": storage_types,
    })


@router.post("/minifigure/{part_id}/add")
async def add_minifigure(
    request:  Request,
    part_id:  str,
    name:     str = Form(""),
    img_url:  str = Form(""),
    location: str = Form(...),
):
    from fastapi.responses import RedirectResponse
    conn = get_db()
    try:
        conn.execute("""
            INSERT INTO parts (part_id, name, known_owned, img_url, item_type)
            VALUES (?, ?, 1, ?, 'minifig')
            ON CONFLICT(part_id) DO UPDATE SET
                name       = COALESCE(excluded.name, name),
                img_url    = COALESCE(NULLIF(excluded.img_url, ''), img_url),
                known_owned = 1,
                item_type  = 'minifig',
                updated_at = datetime('now')
        """, (part_id, name or part_id, img_url or None))

        loc_id = _upsert_location(conn, location)
        conn.execute("""
            INSERT INTO part_locations (part_id, location_id, role, qty)
            VALUES (?, ?, 'primary', 1)
            ON CONFLICT(part_id, location_id) DO UPDATE SET qty = 1
        """, (part_id, loc_id))
        conn.commit()
    finally:
        conn.close()

    return RedirectResponse(f"/minifigure/{part_id}", status_code=303)


@router.post("/minifigure/{part_id}/set-location", response_class=HTMLResponse)
async def set_minifig_location(
    request:  Request,
    part_id:  str,
    location: str = Form(...),
):
    conn = get_db()
    try:
        loc_id = _upsert_location(conn, location)
        conn.execute(
            "DELETE FROM part_locations WHERE part_id = ? AND role = 'primary'",
            (part_id,),
        )
        conn.execute(
            "INSERT INTO part_locations (part_id, location_id, role, qty) VALUES (?, ?, 'primary', 1)",
            (part_id, loc_id),
        )
        conn.execute(
            "UPDATE parts SET updated_at = datetime('now') WHERE part_id = ?",
            (part_id,),
        )
        conn.commit()
        part          = _get_part_with_location(conn, part_id)
        storage_types = _get_storage_types(conn)
    finally:
        conn.close()

    return templates.TemplateResponse("partials/_minifig_location.html", {
        "request":       request,
        "part_id":       part_id,
        "part":          part,
        "storage_types": storage_types,
    })
