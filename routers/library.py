"""
Library browse routes — Category → Subcategory → Part grid.

GET /library                       → 12 BA category tiles with owned-part counts
GET /library/{cat_slug}            → subcategories within a category
GET /library/{cat_slug}/{sub_slug} → 2-col part image grid
"""

import re
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from database import get_db

router = APIRouter()
templates = Jinja2Templates(directory="templates")

# 12 BA categories in display order — slug must stay stable (used in URLs)
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


def _sub_slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


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
            SELECT sc.id, sc.name, COUNT(DISTINCT pc.part_id) AS count
            FROM subcategories sc
            LEFT JOIN part_categories pc ON sc.id = pc.subcategory_id
            WHERE sc.category_id = ?
            GROUP BY sc.id, sc.name
            ORDER BY sc.name
        """, (cat_id,)).fetchall()

        subcategories = [
            {"slug": _sub_slug(r["name"]), "name": r["name"], "count": r["count"]}
            for r in rows
        ]
        total = conn.execute("""
            SELECT COUNT(DISTINCT pc.part_id)
            FROM part_categories pc
            WHERE pc.category_id = ?
        """, (cat_id,)).fetchone()[0]
    finally:
        conn.close()

    return templates.TemplateResponse("library_category.html", {
        "request":       request,
        "cat_slug":      cat_slug,
        "cat_name":      cat_name,
        "subcategories": subcategories,
        "total":         total,
    })


@router.get("/library/{cat_slug}/{sub_slug}", response_class=HTMLResponse)
async def library_subcategory(request: Request, cat_slug: str, sub_slug: str):
    cat_name = SLUG_TO_NAME.get(cat_slug)
    if not cat_name:
        return HTMLResponse("Category not found", status_code=404)

    conn = get_db()
    try:
        cat_row = conn.execute(
            "SELECT id FROM categories WHERE name = ?", (cat_name,)
        ).fetchone()
        if not cat_row:
            return HTMLResponse("Category not in database", status_code=404)
        cat_id = cat_row["id"]

        # Match slug against all subcategories in this category
        sub_rows = conn.execute(
            "SELECT id, name FROM subcategories WHERE category_id = ?", (cat_id,)
        ).fetchall()
        sub_row = next(
            (r for r in sub_rows if _sub_slug(r["name"]) == sub_slug), None
        )
        if not sub_row:
            return HTMLResponse("Subcategory not found", status_code=404)
        sub_id   = sub_row["id"]
        sub_name = sub_row["name"]

        parts = conn.execute("""
            SELECT
                p.part_id, p.name, p.img_url,
                st.code AS storage_code,
                st.name AS storage_name
            FROM parts p
            JOIN part_categories pc ON p.part_id = pc.part_id
            LEFT JOIN part_locations pl ON p.part_id = pl.part_id AND pl.role = 'primary'
            LEFT JOIN locations l       ON pl.location_id = l.id
            LEFT JOIN storage_types st  ON l.storage_type_id = st.id
            WHERE pc.subcategory_id = ?
            ORDER BY p.name
        """, (sub_id,)).fetchall()
        parts_list = [dict(r) for r in parts]
    finally:
        conn.close()

    return templates.TemplateResponse("library_subcategory.html", {
        "request":  request,
        "cat_slug": cat_slug,
        "cat_name": cat_name,
        "sub_slug": sub_slug,
        "sub_name": sub_name,
        "parts":    parts_list,
    })
