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
            id          INTEGER PRIMARY KEY,
            code        TEXT UNIQUE NOT NULL,
            type        TEXT NOT NULL,
            description TEXT
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

    _seed_demo_data(conn)
    conn.commit()
    conn.close()


def _seed_demo_data(conn: sqlite3.Connection) -> None:
    """
    Pre-seed two demo parts (3001, 3710) so the 'found' flow works immediately.
    Uses INSERT OR IGNORE so re-runs are safe.
    """
    # Seed categories
    conn.execute("INSERT OR IGNORE INTO categories (name) VALUES ('Basic')")
    conn.execute("INSERT OR IGNORE INTO categories (name) VALUES ('Plates')")

    basic_id = conn.execute(
        "SELECT id FROM categories WHERE name = 'Basic'"
    ).fetchone()["id"]
    plates_id = conn.execute(
        "SELECT id FROM categories WHERE name = 'Plates'"
    ).fetchone()["id"]

    # Seed subcategories
    conn.execute(
        "INSERT OR IGNORE INTO subcategories (category_id, name) VALUES (?, '2× Brick')",
        (basic_id,),
    )
    conn.execute(
        "INSERT OR IGNORE INTO subcategories (category_id, name) VALUES (?, '1× Plate')",
        (plates_id,),
    )

    brick_sub_id = conn.execute(
        "SELECT id FROM subcategories WHERE name = '2× Brick'"
    ).fetchone()["id"]
    plate_sub_id = conn.execute(
        "SELECT id FROM subcategories WHERE name = '1× Plate'"
    ).fetchone()["id"]

    # Seed locations
    conn.execute(
        "INSERT OR IGNORE INTO locations (code, type, description) VALUES ('A3', 'akro_drawer', 'Akro-Mils drawer A3')"
    )
    conn.execute(
        "INSERT OR IGNORE INTO locations (code, type, description) VALUES ('B7', 'akro_drawer', 'Akro-Mils drawer B7')"
    )

    a3_id = conn.execute(
        "SELECT id FROM locations WHERE code = 'A3'"
    ).fetchone()["id"]
    b7_id = conn.execute(
        "SELECT id FROM locations WHERE code = 'B7'"
    ).fetchone()["id"]

    # Seed parts
    conn.execute("""
        INSERT OR IGNORE INTO parts (part_id, name, known_owned, img_url)
        VALUES ('3001', '2×4 Brick', 1, NULL)
    """)
    conn.execute("""
        INSERT OR IGNORE INTO parts (part_id, name, known_owned, img_url)
        VALUES ('3710', '1×4 Plate', 1, NULL)
    """)

    # Seed part → category mappings
    conn.execute("""
        INSERT OR IGNORE INTO part_categories (part_id, category_id, subcategory_id)
        VALUES ('3001', ?, ?)
    """, (basic_id, brick_sub_id))
    conn.execute("""
        INSERT OR IGNORE INTO part_categories (part_id, category_id, subcategory_id)
        VALUES ('3710', ?, ?)
    """, (plates_id, plate_sub_id))

    # Seed part → location mappings
    conn.execute("""
        INSERT OR IGNORE INTO part_locations (part_id, location_id, role, qty)
        VALUES ('3001', ?, 'primary', 47)
    """, (a3_id,))
    conn.execute("""
        INSERT OR IGNORE INTO part_locations (part_id, location_id, role, qty)
        VALUES ('3710', ?, 'primary', 12)
    """, (b7_id,))
