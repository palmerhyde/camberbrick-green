"""
Collection CRUD routes.

GET  /collection?id=3001   → check if a part is owned
GET  /collection            → list all parts with locations
POST /collection            → add a new part
PATCH /collection/{part_id} → update qty or location for a part
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional
from database import get_db

router = APIRouter()


# ── Pydantic models ────────────────────────────────────────────────────────────

class AddPartRequest(BaseModel):
    id: str
    name: Optional[str] = None
    qty: Optional[int] = 1
    location: str
    category: Optional[str] = ""


class UpdatePartRequest(BaseModel):
    qty: Optional[int] = None
    location: Optional[str] = None


# ── Helpers ────────────────────────────────────────────────────────────────────

def _get_part_with_location(conn, part_id: str) -> Optional[dict]:
    """Return a part dict including its primary location, or None."""
    row = conn.execute("""
        SELECT
            p.part_id, p.name, p.img_url,
            c.name   AS category,
            sc.name  AS subcategory,
            l.code   AS location,
            l.type   AS location_type,
            st.code  AS storage_code,
            st.name  AS storage_name,
            pl.role,
            pl.qty
        FROM parts p
        LEFT JOIN part_categories pc  ON p.part_id = pc.part_id
        LEFT JOIN categories c        ON pc.category_id = c.id
        LEFT JOIN subcategories sc    ON pc.subcategory_id = sc.id
        LEFT JOIN part_locations pl   ON p.part_id = pl.part_id AND pl.role = 'primary'
        LEFT JOIN locations l         ON pl.location_id = l.id
        LEFT JOIN storage_types st    ON l.storage_type_id = st.id
        WHERE p.part_id = ?
    """, (part_id,)).fetchone()

    if row is None:
        return None

    # Also fetch overflow locations
    overflow = conn.execute("""
        SELECT l.code, l.type, pl.qty
        FROM part_locations pl
        JOIN locations l ON pl.location_id = l.id
        WHERE pl.part_id = ? AND pl.role = 'overflow'
    """, (part_id,)).fetchall()

    return {
        "part_id":       row["part_id"],
        "name":          row["name"],
        "img_url":       row["img_url"],
        "category":      row["category"],
        "subcategory":   row["subcategory"],
        "location":      row["location"],
        "location_type": row["location_type"],
        "storage_code":  row["storage_code"],
        "storage_name":  row["storage_name"],
        "qty":           row["qty"] or 0,
        "overflow":      [{"location": o["code"], "type": o["type"], "qty": o["qty"]} for o in overflow],
    }


def _upsert_part_category(conn, part_id: str, category_str: str) -> None:
    """Parse a BA breadcrumb like 'Basic › Brick' and save to part_categories."""
    if not category_str:
        return
    segments = [s.strip() for s in category_str.split("›")]
    cat_name = segments[0] if segments else ""
    sub_name = segments[1] if len(segments) > 1 else ""
    if not cat_name:
        return
    cat_row = conn.execute(
        "SELECT id FROM categories WHERE name = ?", (cat_name,)
    ).fetchone()
    if not cat_row:
        return
    cat_id = cat_row["id"]
    sub_id = None
    if sub_name:
        sub_row = conn.execute(
            "SELECT id FROM subcategories WHERE category_id = ? AND name = ?",
            (cat_id, sub_name),
        ).fetchone()
        if sub_row:
            sub_id = sub_row["id"]
    conn.execute("""
        INSERT INTO part_categories (part_id, category_id, subcategory_id)
        VALUES (?, ?, ?)
        ON CONFLICT(part_id) DO UPDATE SET
            category_id    = excluded.category_id,
            subcategory_id = excluded.subcategory_id
    """, (part_id, cat_id, sub_id))


def _get_or_create_location(conn, code: str) -> int:
    """Return location id for code, creating an untyped entry if new."""
    row = conn.execute("SELECT id FROM locations WHERE code = ?", (code,)).fetchone()
    if row:
        return row["id"]
    conn.execute(
        "INSERT INTO locations (code, type, description) VALUES (?, 'temporary', ?)",
        (code, f"Auto-created for part entry"),
    )
    return conn.execute("SELECT id FROM locations WHERE code = ?", (code,)).fetchone()["id"]


# ── Routes ─────────────────────────────────────────────────────────────────────

@router.get("/collection")
def get_collection(id: Optional[str] = None):
    conn = get_db()
    try:
        if id:
            part = _get_part_with_location(conn, id)
            return {"found": part is not None, "part": part}

        rows = conn.execute("SELECT part_id FROM parts ORDER BY part_id").fetchall()
        parts = [_get_part_with_location(conn, r["part_id"]) for r in rows]
        return {"parts": [p for p in parts if p]}
    finally:
        conn.close()


@router.post("/collection")
def add_to_collection(body: AddPartRequest):
    if not body.location:
        raise HTTPException(status_code=400, detail="location is required")

    conn = get_db()
    try:
        # Upsert part
        conn.execute("""
            INSERT INTO parts (part_id, name, known_owned)
            VALUES (?, ?, 1)
            ON CONFLICT(part_id) DO UPDATE SET
                name = excluded.name,
                updated_at = datetime('now')
        """, (body.id, body.name or body.id))

        # Get or create location
        loc_id = _get_or_create_location(conn, body.location)

        # Upsert primary location
        conn.execute("""
            INSERT INTO part_locations (part_id, location_id, role, qty)
            VALUES (?, ?, 'primary', ?)
            ON CONFLICT(part_id, location_id) DO UPDATE SET qty = excluded.qty
        """, (body.id, loc_id, body.qty or 1))

        conn.commit()
        part = _get_part_with_location(conn, body.id)
        return {"part": part}
    finally:
        conn.close()


@router.patch("/collection/{part_id}")
def update_part(part_id: str, body: UpdatePartRequest):
    conn = get_db()
    try:
        existing = _get_part_with_location(conn, part_id)
        if not existing:
            raise HTTPException(status_code=404, detail=f"Part {part_id} not in collection")

        if body.qty is not None:
            conn.execute("""
                UPDATE part_locations SET qty = ?
                WHERE part_id = ? AND role = 'primary'
            """, (body.qty, part_id))

        if body.location is not None:
            loc_id = _get_or_create_location(conn, body.location)
            # Remove old primary, insert new one
            conn.execute(
                "DELETE FROM part_locations WHERE part_id = ? AND role = 'primary'",
                (part_id,),
            )
            conn.execute("""
                INSERT INTO part_locations (part_id, location_id, role, qty)
                VALUES (?, ?, 'primary', ?)
            """, (part_id, loc_id, body.qty or existing["qty"]))

        conn.execute(
            "UPDATE parts SET updated_at = datetime('now') WHERE part_id = ?",
            (part_id,),
        )
        conn.commit()
        part = _get_part_with_location(conn, part_id)
        return {"part": part}
    finally:
        conn.close()
