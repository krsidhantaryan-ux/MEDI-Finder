"""
MediFinder — Database setup, migrations, and connection helpers.
A single SQLite file keeps the whole platform zero-config while still
supporting customers, shops, inventory, reservations, reviews,
favourites, and an audit log.
"""
import sqlite3
from flask import g, current_app

SCHEMA = """
CREATE TABLE IF NOT EXISTS customers (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    name            TEXT NOT NULL,
    email           TEXT UNIQUE NOT NULL COLLATE NOCASE,
    phone           TEXT,
    password_hash   TEXT NOT NULL,
    lat             REAL,
    lng             REAL,
    city            TEXT,
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS shops (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    name            TEXT UNIQUE NOT NULL,
    email           TEXT,
    phone           TEXT,
    password_hash   TEXT NOT NULL,
    owner_name      TEXT,
    license_number  TEXT,
    license_image   TEXT,
    gst_certificate TEXT,
    shop_photo      TEXT,
    description     TEXT DEFAULT '',
    address         TEXT,
    city            TEXT,
    state           TEXT,
    pincode         TEXT,
    lat             REAL,
    lng             REAL,
    open_time       TEXT DEFAULT '09:00',
    close_time      TEXT DEFAULT '21:00',
    is_open_24h     INTEGER DEFAULT 0,
    delivery        INTEGER DEFAULT 0,
    status          TEXT DEFAULT 'Pending',
    rejection_note  TEXT,
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS categories (
    id      INTEGER PRIMARY KEY AUTOINCREMENT,
    name    TEXT UNIQUE NOT NULL,
    slug    TEXT UNIQUE NOT NULL,
    icon    TEXT DEFAULT 'bi-capsule'
);

CREATE TABLE IF NOT EXISTS inventory (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    shop_id         INTEGER NOT NULL,
    med_name        TEXT NOT NULL,
    salt_composition TEXT DEFAULT '',
    category_id     INTEGER REFERENCES categories(id) ON DELETE SET NULL,
    manufacturer    TEXT DEFAULT '',
    batch_no        TEXT DEFAULT '',
    expiry_date     TEXT,
    price           REAL DEFAULT 0,
    mrp             REAL DEFAULT 0,
    stock_quantity  INTEGER DEFAULT 0,
    dosage          TEXT DEFAULT '',
    prescription    INTEGER DEFAULT 0,
    is_active       INTEGER DEFAULT 1,
    updated_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (shop_id) REFERENCES shops(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS reservations (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    inventory_id    INTEGER NOT NULL,
    shop_id         INTEGER NOT NULL,
    customer_id     INTEGER REFERENCES customers(id) ON DELETE SET NULL,
    customer_name   TEXT,
    customer_phone  TEXT NOT NULL,
    quantity        INTEGER DEFAULT 1,
    status          TEXT DEFAULT 'Pending',  -- Pending | Confirmed | Collected | Cancelled | Expired
    note            TEXT,
    held_until      TIMESTAMP,
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (inventory_id) REFERENCES inventory(id) ON DELETE CASCADE,
    FOREIGN KEY (shop_id) REFERENCES shops(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS reviews (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    shop_id      INTEGER NOT NULL,
    customer_id  INTEGER REFERENCES customers(id) ON DELETE SET NULL,
    customer_name TEXT,
    rating       INTEGER NOT NULL CHECK(rating BETWEEN 1 AND 5),
    comment      TEXT,
    created_at   TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (shop_id) REFERENCES shops(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS favourites (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    customer_id INTEGER NOT NULL,
    med_name    TEXT NOT NULL,
    salt        TEXT DEFAULT '',
    created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(customer_id, med_name, salt),
    FOREIGN KEY (customer_id) REFERENCES customers(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS activity_log (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    actor_type  TEXT,        -- 'customer' | 'shop' | 'admin'
    actor_id    INTEGER,
    action      TEXT,
    detail      TEXT,
    created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
"""

INDEXES = [
    "CREATE INDEX IF NOT EXISTS idx_inv_shop ON inventory(shop_id)",
    "CREATE INDEX IF NOT EXISTS idx_inv_name ON inventory(med_name)",
    "CREATE INDEX IF NOT EXISTS idx_inv_salt ON inventory(salt_composition)",
    "CREATE INDEX IF NOT EXISTS idx_inv_active ON inventory(is_active, stock_quantity)",
    "CREATE INDEX IF NOT EXISTS idx_res_shop ON reservations(shop_id, status)",
    "CREATE INDEX IF NOT EXISTS idx_res_inv ON reservations(inventory_id)",
    "CREATE INDEX IF NOT EXISTS idx_reviews_shop ON reviews(shop_id)",
    "CREATE INDEX IF NOT EXISTS idx_shops_status ON shops(status)",
]

# Columns that may be missing from the old database — added idempotently.
MIGRATIONS = {
    "shops": [
        ("email", "TEXT"), ("phone", "TEXT"), ("owner_name", "TEXT"),
        ("description", "TEXT DEFAULT ''"), ("address", "TEXT"),
        ("state", "TEXT"), ("pincode", "TEXT"),
        ("open_time", "TEXT DEFAULT '09:00'"),
        ("close_time", "TEXT DEFAULT '21:00'"),
        ("is_open_24h", "INTEGER DEFAULT 0"),
        ("delivery", "INTEGER DEFAULT 0"),
        ("rejection_note", "TEXT"),
    ],
    "inventory": [
        ("category_id", "INTEGER"),
        ("manufacturer", "TEXT DEFAULT ''"),
        ("batch_no", "TEXT DEFAULT ''"),
        ("expiry_date", "TEXT"),
        ("mrp", "REAL DEFAULT 0"),
        ("prescription", "INTEGER DEFAULT 0"),
        ("is_active", "INTEGER DEFAULT 1"),
        ("updated_at", "TIMESTAMP DEFAULT CURRENT_TIMESTAMP"),
    ],
    "reservations": [
        ("shop_id", "INTEGER"),
        ("customer_id", "INTEGER"),
        ("customer_name", "TEXT"),
        ("quantity", "INTEGER DEFAULT 1"),
        ("note", "TEXT"),
        ("held_until", "TIMESTAMP"),
        ("updated_at", "TIMESTAMP DEFAULT CURRENT_TIMESTAMP"),
    ],
    "customers": [],
    "reviews": [],
    "favourites": [],
    "categories": [],
    "activity_log": [],
}


def get_db():
    """Return a request-scoped SQLite connection."""
    if "db" not in g:
        conn = sqlite3.connect(current_app.config["DATABASE"])
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON;")
        g.db = conn
    return g.db


def close_db(exc=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def _columns(conn, table):
    return {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}


def init_db():
    """Create tables, run idempotent migrations, and create indexes."""
    conn = sqlite3.connect(current_app.config["DATABASE"])
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    try:
        conn.executescript(SCHEMA)

        for table, cols in MIGRATIONS.items():
            existing = _columns(conn, table)
            for name, decl in cols:
                if name not in existing:
                    conn.execute(f"ALTER TABLE {table} ADD COLUMN {name} {decl}")

        for ddl in INDEXES:
            conn.execute(ddl)

        conn.commit()
    finally:
        conn.close()


CATEGORIES = [
    ("Tablets & Capsules", "tablets", "bi-capsule"),
    ("Syrups & Liquids", "syrups", "bi-droplet"),
    ("Injections", "injections", "bi-eyedropper"),
    ("Topicals & Creams", "topicals", "bi-bandaid"),
    ("Cough & Cold", "cough-cold", "bi-thermometer"),
    ("Diabetes Care", "diabetes", "bi-activity"),
    ("Cardiac", "cardiac", "bi-heart-pulse"),
    ("Vitamins & Supplements", "vitamins", "bi-capsule-pill"),
    ("Ayurvedic & Herbal", "ayurvedic", "bi-flower1"),
    ("Baby & Maternity", "baby", "bi-emoji-smile"),
    ("Medical Devices", "devices", "bi-broadcast"),
    ("Personal Care", "personal-care", "bi-heart"),
]


def seed_categories(conn):
    for name, slug, icon in CATEGORIES:
        conn.execute(
            "INSERT OR IGNORE INTO categories (name, slug, icon) VALUES (?, ?, ?)",
            (name, slug, icon),
        )
    conn.commit()
