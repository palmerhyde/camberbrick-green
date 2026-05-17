"""
Library browse routes — Category → Parts (BA-style grouped page).

GET /library                       → 12 BA category tiles with owned-part counts
GET /library/{cat_slug}            → all parts in category, grouped by subcategory then group
GET /library/{cat_slug}/{sub_slug} → redirects to category page (old URL compat)
"""

import re
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from database import get_db


def _slugify(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")


def _size_sort_key(part: dict) -> tuple:
    """Sort key that extracts stud dimensions from names like 'Brick 1 x 4'.
    Returns (longest_dim, shortest_dim, name) so 1×2 < 1×4 < 2×4 < 2×6."""
    name = part.get("name") or ""
    m = re.search(r"(\d+)\s*[xX×]\s*(\d+)", name)
    if m:
        a, b = int(m.group(1)), int(m.group(2))
        return (max(a, b), min(a, b), name)
    # No dimension found — sort after dimensioned parts, then by name/id
    return (999, 999, name or part.get("part_id", ""))

router = APIRouter()
templates = Jinja2Templates(directory="templates")

BA_CATEGORIES = [
    ("basic",        "Basic"),
    ("wall",         "Wall"),
    ("snot",         "SNOT"),
    ("angle",        "Angle"),
    ("curve",        "Curve"),
    ("articulation", "Articulation"),
    ("minifig",      "Minifig"),
    ("nature",       "Nature"),
    ("vehicle",      "Vehicle"),
    ("technic",      "Technic"),
    ("electronics",  "Electronics"),
    ("duplo",        "DUPLO"),
]
SLUG_TO_NAME = {slug: name for slug, name in BA_CATEGORIES}


@router.get("/library", response_class=HTMLResponse)
async def library_index(request: Request):
    conn = get_db()
    try:
        rows = conn.execute("""
            SELECT c.name, COUNT(DISTINCT pc.part_id) AS count
            FROM categories c
            LEFT JOIN part_categories pc ON c.id = pc.category_id
            GROUP BY c.id
        """).fetchall()
        counts = {r["name"]: r["count"] for r in rows}
    finally:
        conn.close()

    categories = [
        {"slug": slug, "name": name, "count": counts.get(name, 0)}
        for slug, name in BA_CATEGORIES
    ]
    return templates.TemplateResponse("library.html", {
        "request":    request,
        "categories": categories,
    })


@router.get("/library/{cat_slug}", response_class=HTMLResponse)
async def library_category(request: Request, cat_slug: str):
    cat_name = SLUG_TO_NAME.get(cat_slug)
    if not cat_name:
        return HTMLResponse("Category not found", status_code=404)

    conn = get_db()
    try:
        cat_row = conn.execute(
            "SELECT id FROM categories WHERE name = ?", (cat_name,)
        ).fetchone()
        if not cat_row:
            return HTMLResponse("Category not yet in database — restart the server to seed.", status_code=404)
        cat_id = cat_row["id"]

        rows = conn.execute("""
            SELECT
                p.part_id, p.name, p.img_url,
                sc.name AS subcategory_name,
                pc.group_name,
                COALESCE(st.code, l.code) AS storage_code
            FROM parts p
            JOIN part_categories pc ON p.part_id = pc.part_id
            JOIN subcategories sc   ON pc.subcategory_id = sc.id
            LEFT JOIN part_locations pl ON p.part_id = pl.part_id AND pl.role = 'primary'
            LEFT JOIN locations l       ON pl.location_id = l.id
            LEFT JOIN storage_types st  ON l.storage_type_id = st.id
            WHERE pc.category_id = ?
            ORDER BY sc.name, COALESCE(pc.group_name, ''), p.name
        """, (cat_id,)).fetchall()
    finally:
        conn.close()

    # Build nested structure: [{name, groups: [{name, parts: [...]}]}]
    sections = {}
    sub_order = []
    group_order = {}

    for row in rows:
        sub  = row["subcategory_name"]
        grp  = row["group_name"] or ""

        if sub not in sections:
            sections[sub] = {}
            sub_order.append(sub)
            group_order[sub] = []

        if grp not in sections[sub]:
            sections[sub][grp] = []
            group_order[sub].append(grp)

        sections[sub][grp].append(dict(row))

    # Sort parts within each group by physical size
    for sub in sections:
        for grp in sections[sub]:
            sections[sub][grp].sort(key=_size_sort_key)

    sections_list = [
        {
            "name": sub,
            "slug": _slugify(sub),
            "groups": [
                {"name": grp, "parts": sections[sub][grp]}
                for grp in group_order[sub]
            ],
            "total": sum(len(sections[sub][grp]) for grp in group_order[sub]),
        }
        for sub in sub_order
    ]
    total = sum(s["total"] for s in sections_list)

    return templates.TemplateResponse("library_category.html", {
        "request":  request,
        "cat_slug": cat_slug,
        "cat_name": cat_name,
        "sections": sections_list,
        "total":    total,
    })


@router.get("/library/{cat_slug}/{sub_slug}", response_class=HTMLResponse)
async def library_subcategory_redirect(request: Request, cat_slug: str, sub_slug: str):
    return RedirectResponse(f"/library/{cat_slug}", status_code=301)
