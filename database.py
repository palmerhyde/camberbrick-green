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

    _seed_storage_types(conn)
    _seed_taxonomy(conn)
    conn.commit()
    conn.close()


# Full Brick Architect taxonomy — 12 top-level categories with subcategories.
# Names must match BA's breadcrumb anchor text exactly so the scraper can map parts.
_BA_TAXONOMY: dict[str, list[str]] = {
    "Basic":        ["Brick", "Plate", "Tile", "Slope", "Wedge",
                     "Round", "Arch", "Modified Brick", "Modified Plate", "Modified Tile"],
    "Wall":         ["Panel", "Window", "Door", "Fence"],
    "SNOT":         ["Bracket", "Modified Brick", "Modified Plate"],
    "Angle":        ["Hinge", "Turntable", "Swivel Plate"],
    "Curve":        ["Arch", "Dome", "Cylinder"],
    "Articulation": ["Ball Joint", "Bar & Clip", "Tow Ball", "Pin & Connector"],
    "Minifig":      ["Head", "Torso", "Leg", "Accessory", "Hair & Hat", "Visor & Helmet"],
    "Nature":       ["Plant", "Animal", "Rock & Ground"],
    "Vehicle":      ["Wheel & Tyre", "Axle & Mudguard", "Cockpit & Windscreen", "Hull & Body"],
    "Technic":      ["Beam", "Connector", "Gear", "Pin & Axle", "Panel & Plate"],
    "Electronics":  ["Brick & Hub", "Light", "Motor & Servo"],
    "DUPLO":        ["Brick", "Figure", "Animal & Nature", "Vehicle & Accessory"],
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
    """Seed the full BA taxonomy into categories / subcategories. Safe to re-run."""
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
