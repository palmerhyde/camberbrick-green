"""
SQLite database setup for Camberbrick Green.
Initialises the schema on startup and provides a connection helper.
"""

import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).parent / "data" / "collection.db"


def get_db() -> sqlite3.Connection:
    """Return a connection with row_factory set so rows behave like dicts."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db() -> None:
    """Create tables if they don't exist and seed demo data."""
    DB_PATH.parent.mkdir(exist_ok=True)
    conn = get_db()

    conn.executescript("""
        CREATE TABLE IF NOT EXISTS storage_types (
            id           INTEGER PRIMARY KEY,
            name         TEXT UNIQUE NOT NULL,
            code         TEXT,
            photo_path   TEXT,
            purchase_url TEXT,
            notes        TEXT,
            sort_order   INTEGER DEFAULT 0,
            created_at   TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS parts (
            part_id          TEXT PRIMARY KEY,
            name             TEXT,
            known_owned      BOOLEAN DEFAULT 1,
            brickognize_name TEXT,
            img_url          TEXT,
            created_at       TEXT DEFAULT (datetime('now')),
            updated_at       TEXT DEFAULT (datetime('now'))
        );

        CREATE TABLE IF NOT EXISTS categories (
            id   INTEGER PRIMARY KEY,
            name TEXT UNIQUE NOT NULL
        );

        CREATE TABLE IF NOT EXISTS subcategories (
            id          INTEGER PRIMARY KEY,
            category_id INTEGER NOT NULL REFERENCES categories(id),
            name        TEXT NOT NULL,
            UNIQUE(category_id, name)
        );

        CREATE TABLE IF NOT EXISTS locations (
            id              INTEGER PRIMARY KEY,
            code            TEXT UNIQUE NOT NULL,
            type            TEXT NOT NULL,
            description     TEXT,
            storage_type_id INTEGER REFERENCES storage_types(id)
        );

        CREATE TABLE IF NOT EXISTS part_categories (
            part_id        TEXT PRIMARY KEY REFERENCES parts(part_id),
            category_id    INTEGER REFERENCES categories(id),
            subcategory_id INTEGER REFERENCES subcategories(id)
        );

        CREATE TABLE IF NOT EXISTS part_locations (
            part_id     TEXT    NOT NULL REFERENCES parts(part_id),
            location_id INTEGER NOT NULL REFERENCES locations(id),
            role        TEXT    DEFAULT 'primary',
            qty         INTEGER DEFAULT 1,
            notes       TEXT,
            PRIMARY KEY (part_id, location_id)
        );
    """)

    # Migrate locations table if storage_type_id column is missing
    loc_cols = [r[1] for r in conn.execute("PRAGMA table_info(locations)").fetchall()]
    if "storage_type_id" not in loc_cols:
        conn.execute("ALTER TABLE locations ADD COLUMN storage_type_id INTEGER REFERENCES storage_types(id)")

    # Migrate storage_types table if code column is missing
    st_cols = [r[1] for r in conn.execute("PRAGMA table_info(storage_types)").fetchall()]
    if "code" not in st_cols:
        conn.execute("ALTER TABLE storage_types ADD COLUMN code TEXT")

    # Migrate parts table if ba_category column is missing
    p_cols = [r[1] for r in conn.execute("PRAGMA table_info(parts)").fetchall()]
    if "ba_category" not in p_cols:
        conn.execute("ALTER TABLE parts ADD COLUMN ba_category TEXT")

    # Migrate part_categories if group_name column is missing (3rd BA level)
    pc_cols = [r[1] for r in conn.execute("PRAGMA table_info(part_categories)").fetchall()]
    if "group_name" not in pc_cols:
        conn.execute("ALTER TABLE part_categories ADD COLUMN group_name TEXT")

    _seed_storage_types(conn)
    _seed_taxonomy(conn)
    _backfill_group_names(conn)
    conn.commit()
    conn.close()


# Full Brick Architect taxonomy — scraped directly from brickarchitect.com/parts/
# Subcategory names match BA's breadcrumb level-2 anchor text exactly.
_BA_TAXONOMY: dict[str, list[str]] = {
    "Basic":        ["Brick", "Plate", "Blate", "Tile", "Baseplate", "Other"],
    "Wall":         ["Window & Door", "Panel", "Decorative", "Fence", "Structural", "Stairs", "Container"],
    "SNOT":         ["Brick", "Bracket", "Jumper"],
    "Angle":        ["Slope", "Wedge", "Wedge Slope"],
    "Curve":        ["Curved Brick", "Curved Plate", "Curved Blate", "Curved Tile",
                     "Cylinder", "Cone", "Dish and Dome", "Ball", "Curved",
                     "Arch", "Wedge", "Windscreen", "Mudguard", "Heart & Star", "Other Curved Parts"],
    "Articulation": ["Rotation", "Clip", "Ball & Socket", "Rail & Groove", "Flexible", "Other"],
    "Minifig":      ["Minifigure", "Minidoll", "Other Figs", "Hair", "Clothing",
                     "Accessories", "Container", "Weapons", "Clikits"],
    "Nature":       ["Plants", "Flowers", "Produce", "Animal", "Tooth",
                     "Barb, Horn, Tail & Feather", "Web", "Elemental"],
    "Vehicle":      ["Wheel", "Wheel Pin", "Vehicle Base", "Nose & Roof", "Train",
                     "Coaster", "Stuntz", "Steering", "Propeller & Engine", "Fin & Wing"],
    "Technic":      ["Brick", "Plate", "Beam", "Thin Beam", "Panel", "Connector",
                     "Gears", "Link & Chain", "Steering", "Engine",
                     "Mechanical & Pneumatic", "Other Technic"],
    "Electronics":  ["Hubs", "Motors", "Sensor & Accessories", "Bluetooth",
                     "Dimensions", "Standalone Electronics", "Smart Play"],
    "DUPLO":        ["Brick", "Plate", "Wall", "Angle", "Curved", "Ball Tube",
                     "Accessories and Nature", "Other", "QUATRO", "PRIMO"],
}


def _seed_storage_types(conn: sqlite3.Connection) -> None:
    """Seed default storage types once — never overwrites user data."""
    if conn.execute("SELECT COUNT(*) FROM storage_types").fetchone()[0] == 0:
        defaults = [
            ("Akro-Mils 64-drawer", "AL", 1),
            ("Akro-Mils 24-drawer", "AS", 2),
            ("Bead boxes",          "BB", 3),
            ("Shoe boxes",          "SS", 4),
            ("Overflow",            "OF", 5),
        ]
        for name, code, order in defaults:
            conn.execute(
                "INSERT INTO storage_types (name, code, sort_order) VALUES (?, ?, ?)",
                (name, code, order),
            )


def _seed_taxonomy(conn: sqlite3.Connection) -> None:
    """Seed the full BA taxonomy. Adds missing entries and removes stale ones."""
    for cat_name, subcats in _BA_TAXONOMY.items():
        conn.execute("INSERT OR IGNORE INTO categories (name) VALUES (?)", (cat_name,))
        cat_id = conn.execute(
            "SELECT id FROM categories WHERE name = ?", (cat_name,)
        ).fetchone()["id"]
        for sub_name in subcats:
            conn.execute(
                "INSERT OR IGNORE INTO subcategories (category_id, name) VALUES (?, ?)",
                (cat_id, sub_name),
            )
        # Remove subcategories that are no longer in the taxonomy
        placeholders = ",".join("?" * len(subcats))
        stale_ids = conn.execute(
            f"SELECT id FROM subcategories WHERE category_id = ? AND name NOT IN ({placeholders})",
            [cat_id] + list(subcats),
        ).fetchall()
        for row in stale_ids:
            conn.execute("DELETE FROM part_categories WHERE subcategory_id = ?", (row["id"],))
            conn.execute("DELETE FROM subcategories WHERE id = ?", (row["id"],))


def _backfill_group_names(conn: sqlite3.Connection) -> None:
    """Fill group_name in part_categories from stored ba_category — no network needed."""
    rows = conn.execute("""
        SELECT p.part_id, p.ba_category
        FROM parts p
        JOIN part_categories pc ON p.part_id = pc.part_id
        WHERE pc.group_name IS NULL AND p.ba_category IS NOT NULL
    """).fetchall()
    for row in rows:
        levels = [lvl.strip() for lvl in row["ba_category"].split(" › ")]
        if len(levels) >= 3:
            conn.execute(
                "UPDATE part_categories SET group_name = ? WHERE part_id = ?",
                (levels[2], row["part_id"]),
            )


def get_parts_missing_ba_category() -> list[str]:
    """Return part_ids that are in part_categories but have no ba_category stored."""
    conn = get_db()
    try:
        rows = conn.execute("""
            SELECT p.part_id
            FROM parts p
            JOIN part_categories pc ON p.part_id = pc.part_id
            WHERE p.ba_category IS NULL
        """).fetchall()
        return [r["part_id"] for r in rows]
    finally:
        conn.close()
