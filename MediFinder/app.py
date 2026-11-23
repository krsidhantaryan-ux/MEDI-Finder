import csv
import hmac
import io
import math
import os
import random
import re
import secrets
import sqlite3
import uuid
from datetime import datetime, timedelta, timezone
from urllib.parse import urlparse

from flask import (
    Flask,
    Response,
    g,
    has_app_context,
    jsonify,
    redirect,
    render_template,
    request,
    send_from_directory,
    session,
)
from werkzeug.security import check_password_hash, generate_password_hash
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "medfinder_secure_production_key_2026")

UPLOAD_FOLDER = os.path.join(app.root_path, "static", "uploads")
DEFAULT_DB_PATH = os.environ.get("MEDIFINDER_DB_PATH") or os.path.join(app.root_path, "database.db")

app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER
app.config["DATABASE"] = DEFAULT_DB_PATH
app.config["MAX_CONTENT_LENGTH"] = 16 * 1024 * 1024
app.config["TEMPLATES_AUTO_RELOAD"] = True
app.config["MAX_ACTIVE_HOLDS_PER_PHONE"] = int(os.environ.get("MAX_ACTIVE_HOLDS_PER_PHONE", "5"))
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "webp", "gif", "pdf"}

ADMIN_USERNAME = os.environ.get("ADMIN_USER", "admin")
ADMIN_PASSWORD_HASH = generate_password_hash(os.environ.get("ADMIN_PASS", "admin123"))

IST_OFFSET = timezone(timedelta(hours=5, minutes=30))

SCHEDULE_H_SALT_KEYWORDS = {
    "azithromycin",
    "amoxicillin",
    "clavulanic",
    "ciprofloxacin",
    "ofloxacin",
    "cefixime",
    "cefuroxime",
    "cephalexin",
    "doxycycline",
    "metronidazole",
    "linezolid",
    "gliclazide",
    "metformin",
    "glimepiride",
    "sitagliptin",
    "vildagliptin",
    "dapagliflozin",
    "empagliflozin",
    "insulin",
    "amlodipine",
    "telmisartan",
    "losartan",
    "olmesartan",
    "atenolol",
    "metoprolol",
    "bisoprolol",
    "atorvastatin",
    "rosuvastatin",
    "clopidogrel",
    "warfarin",
    "apixaban",
    "rivaroxaban",
    "alprazolam",
    "clonazepam",
    "lorazepam",
    "zolpidem",
    "escitalopram",
    "sertraline",
    "prednisolone",
    "methylprednisolone",
    "dexamethasone",
    "montelukast",
    "levocetirizine",
    "pantoprazole",
    "rabeprazole",
    "esomeprazole",
    "ondansetron",
    "thyroxine",
    "levothyroxine",
    "tramadol",
}

SALT_SYNONYMS = {
    "acetaminophen": "paracetamol",
    "pcm": "paracetamol",
    "acetylsalicylic acid": "aspirin",
    "asa": "aspirin",
    "amoxycillin": "amoxicillin",
    "clavulanate": "clavulanic acid",
    "potassium clavulanate": "clavulanic acid",
}

INTERACTION_RULES = [
    (
        {"aspirin"},
        {"ibuprofen", "diclofenac", "naproxen", "aceclofenac", "ketorolac", "mefenamic acid"},
        "High",
        "Combining Aspirin with an NSAID painkiller increases stomach bleeding risk and can reduce Aspirin's heart-protective effect.",
    ),
    (
        {"aspirin", "clopidogrel"},
        {"warfarin", "apixaban", "rivaroxaban", "dabigatran"},
        "High",
        "Combining antiplatelets (Aspirin/Clopidogrel) with anticoagulants significantly elevates bleeding risk. Confirm with your physician.",
    ),
    (
        {"ibuprofen", "diclofenac", "naproxen", "aceclofenac"},
        {"ibuprofen", "diclofenac", "naproxen", "aceclofenac", "ketorolac"},
        "High",
        "Taking two NSAID anti-inflammatory painkillers together increases gastric ulcer and kidney injury risk without extra pain relief.",
    ),
    (
        {"azithromycin", "ciprofloxacin", "ofloxacin"},
        {"ondansetron", "domperidone"},
        "Moderate",
        "Macrolide/fluoroquinolone antibiotics combined with Ondansetron or Domperidone may prolong heart QT rhythm in susceptible patients.",
    ),
    (
        {"gliclazide", "glimepiride", "metformin"},
        {"ciprofloxacin", "ofloxacin", "levofloxacin"},
        "Moderate",
        "Fluoroquinolone antibiotics taken alongside diabetes medicines can cause sudden blood-sugar swings (hypoglycemia or hyperglycemia).",
    ),
    (
        {"cetirizine", "levocetirizine", "chlorpheniramine"},
        {"alprazolam", "clonazepam", "zolpidem", "tramadol"},
        "Moderate",
        "Combining antihistamines with sedatives or opioid analgesics increases drowsiness and slows alertness. Avoid driving.",
    ),
    (
        {"pantoprazole", "omeprazole", "rabeprazole", "esomeprazole"},
        {"cefixime", "cefuroxime", "iron", "ferrous ascorbate", "ketoconazole"},
        "Low",
        "Acid-suppressing PPIs (e.g. Pantoprazole) can alter stomach-acid absorption of certain oral iron supplements and antifungals.",
    ),
]

_initialized_dbs = set()


# --- DUAL DATABASE ADAPTER (SQLITE DEFAULT + OPTIONAL POSTGRESQL / SUPABASE) --- #

class DictRow(dict):
    """Row supporting both dict key lookup (`row['id']`) and positional indexing (`row[0]`)."""

    def __init__(self, columns, values):
        super().__init__(zip(columns, values))
        self._values = tuple(values)

    def __getitem__(self, key):
        if isinstance(key, int):
            return self._values[key]
        return super().__getitem__(key)


def _translate_sql_for_postgres(sql):
    translated = sql.replace("?", "%s")
    translated = translated.replace("datetime('now', '+2 hours')", "(CURRENT_TIMESTAMP + INTERVAL '2 hours')")
    translated = translated.replace("datetime(created_at, '+2 hours')", "(created_at + INTERVAL '2 hours')")
    translated = translated.replace("datetime('now')", "CURRENT_TIMESTAMP")
    translated = re.sub(r"datetime\(([^)]+)\)", r"\1", translated)
    translated = re.sub(r"\bMAX\s*\(\s*0\s*,", "GREATEST(0,", translated)
    return translated


class PostgresCursorWrapper:
    def __init__(self, raw_cursor):
        self._cur = raw_cursor
        self.lastrowid = None

    def execute(self, sql, params=()):
        pg_sql = _translate_sql_for_postgres(sql)
        is_insert = pg_sql.lstrip().upper().startswith("INSERT ") and "RETURNING " not in pg_sql.upper()
        if is_insert:
            pg_sql = pg_sql.rstrip().rstrip(";") + " RETURNING id"
        self._cur.execute(pg_sql, tuple(params) if params else ())
        if is_insert:
            row = self._cur.fetchone()
            if row is not None:
                self.lastrowid = row[0] if not isinstance(row, dict) else row.get("id")
        return self

    def fetchone(self):
        row = self._cur.fetchone()
        if row is None:
            return None
        cols = [d[0] for d in (self._cur.description or [])]
        return DictRow(cols, row)

    def fetchall(self):
        rows = self._cur.fetchall()
        cols = [d[0] for d in (self._cur.description or [])]
        return [DictRow(cols, r) for r in rows]


class PostgresConnectionWrapper:
    def __init__(self, raw_conn):
        self._conn = raw_conn

    def cursor(self):
        return PostgresCursorWrapper(self._conn.cursor())

    def execute(self, sql, params=()):
        cur = self.cursor()
        cur.execute(sql, params)
        return cur

    def commit(self):
        self._conn.commit()

    def close(self):
        self._conn.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type is None:
            self._conn.commit()
        else:
            self._conn.rollback()
        return False


def get_active_postgres_url():
    if app.config.get("TESTING") and not app.config.get("POSTGRES_URL"):
        return None
    url = (
        app.config.get("POSTGRES_URL")
        or os.environ.get("SUPABASE_DB_URL")
        or os.environ.get("MEDIFINDER_POSTGRES_URL")
        or os.environ.get("DATABASE_URL")
        or ""
    ).strip()
    if url.startswith("postgres://"):
        url = "postgresql://" + url[len("postgres://"):]
    return url if url.startswith("postgresql://") else None


def _connect_postgres(pg_url):
    try:
        import psycopg  # type: ignore
        raw = psycopg.connect(pg_url)
        return PostgresConnectionWrapper(raw)
    except ImportError:
        import psycopg2  # type: ignore
        raw = psycopg2.connect(pg_url)
        return PostgresConnectionWrapper(raw)


def _connect_sqlite(db_path):
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn


def ensure_postgres_schema(conn):
    conn.execute("""
    CREATE TABLE IF NOT EXISTS shops (
        id SERIAL PRIMARY KEY,
        name TEXT UNIQUE NOT NULL,
        city TEXT,
        password TEXT NOT NULL,
        lat DOUBLE PRECISION,
        lng DOUBLE PRECISION,
        status TEXT DEFAULT 'Pending',
        license_number TEXT,
        license_image TEXT,
        gst_certificate TEXT,
        shop_photo TEXT,
        phone TEXT DEFAULT '',
        opening_hours TEXT DEFAULT '',
        address TEXT DEFAULT '',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)
    conn.execute("""
    CREATE TABLE IF NOT EXISTS inventory (
        id SERIAL PRIMARY KEY,
        shop_id INTEGER NOT NULL REFERENCES shops(id) ON DELETE CASCADE,
        med_name TEXT NOT NULL,
        salt_composition TEXT DEFAULT '',
        price DOUBLE PRECISION DEFAULT 0.0,
        stock_quantity INTEGER DEFAULT 0,
        dosage TEXT DEFAULT '',
        rx_required INTEGER DEFAULT 0,
        expiry_date TEXT DEFAULT ''
    )
    """)
    conn.execute("""
    CREATE TABLE IF NOT EXISTS reservations (
        id SERIAL PRIMARY KEY,
        inventory_id INTEGER NOT NULL REFERENCES inventory(id) ON DELETE CASCADE,
        customer_phone TEXT NOT NULL,
        customer_name TEXT DEFAULT '',
        quantity INTEGER DEFAULT 1,
        status TEXT DEFAULT 'Pending',
        pickup_code TEXT DEFAULT '',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        expires_at TIMESTAMP
    )
    """)
    conn.commit()


def ensure_schema(conn):
    conn.execute("""
    CREATE TABLE IF NOT EXISTS shops (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT UNIQUE NOT NULL,
        city TEXT,
        password TEXT NOT NULL,
        lat REAL,
        lng REAL,
        status TEXT DEFAULT 'Pending',
        license_number TEXT,
        license_image TEXT,
        gst_certificate TEXT,
        shop_photo TEXT,
        phone TEXT DEFAULT '',
        opening_hours TEXT DEFAULT '',
        address TEXT DEFAULT '',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)

    conn.execute("""
    CREATE TABLE IF NOT EXISTS inventory (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        shop_id INTEGER NOT NULL,
        med_name TEXT NOT NULL,
        salt_composition TEXT DEFAULT '',
        price REAL DEFAULT 0.0,
        stock_quantity INTEGER DEFAULT 0,
        dosage TEXT DEFAULT '',
        rx_required INTEGER DEFAULT 0,
        expiry_date TEXT DEFAULT '',
        FOREIGN KEY (shop_id) REFERENCES shops(id) ON DELETE CASCADE
    )
    """)

    conn.execute("""
    CREATE TABLE IF NOT EXISTS reservations (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        inventory_id INTEGER NOT NULL,
        customer_phone TEXT NOT NULL,
        customer_name TEXT DEFAULT '',
        quantity INTEGER DEFAULT 1,
        status TEXT DEFAULT 'Pending',
        pickup_code TEXT DEFAULT '',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        expires_at TIMESTAMP,
        FOREIGN KEY (inventory_id) REFERENCES inventory(id) ON DELETE CASCADE
    )
    """)

    shop_cols = {row[1] for row in conn.execute("PRAGMA table_info(shops)").fetchall()}
    for col_name, col_def in [
        ("phone", "TEXT DEFAULT ''"),
        ("opening_hours", "TEXT DEFAULT ''"),
        ("address", "TEXT DEFAULT ''"),
        ("created_at", "TIMESTAMP"),
    ]:
        if col_name not in shop_cols:
            conn.execute(f"ALTER TABLE shops ADD COLUMN {col_name} {col_def}")

    inv_cols = {row[1] for row in conn.execute("PRAGMA table_info(inventory)").fetchall()}
    for col_name, col_def in [
        ("salt_composition", "TEXT DEFAULT ''"),
        ("price", "REAL DEFAULT 0.0"),
        ("stock_quantity", "INTEGER DEFAULT 0"),
        ("dosage", "TEXT DEFAULT ''"),
        ("rx_required", "INTEGER DEFAULT 0"),
        ("expiry_date", "TEXT DEFAULT ''"),
    ]:
        if col_name not in inv_cols:
            conn.execute(f"ALTER TABLE inventory ADD COLUMN {col_name} {col_def}")

    res_cols = {row[1] for row in conn.execute("PRAGMA table_info(reservations)").fetchall()}
    for col_name, col_def in [
        ("customer_name", "TEXT DEFAULT ''"),
        ("quantity", "INTEGER DEFAULT 1"),
        ("status", "TEXT DEFAULT 'Pending'"),
        ("pickup_code", "TEXT DEFAULT ''"),
        ("created_at", "TIMESTAMP"),
        ("expires_at", "TIMESTAMP"),
    ]:
        if col_name not in res_cols:
            conn.execute(f"ALTER TABLE reservations ADD COLUMN {col_name} {col_def}")

    conn.execute("""
        UPDATE reservations
        SET status = 'Pending'
        WHERE status IS NULL OR TRIM(status) = ''
    """)
    conn.execute("""
        UPDATE reservations
        SET quantity = 1
        WHERE quantity IS NULL OR quantity < 1
    """)
    conn.execute("""
        UPDATE reservations
        SET expires_at = datetime(COALESCE(created_at, CURRENT_TIMESTAMP), '+2 hours')
        WHERE expires_at IS NULL AND status = 'Pending'
    """)

    # Backfill pickup codes on any existing Pending reservations missing one
    missing_codes = conn.execute(
        "SELECT id FROM reservations WHERE pickup_code IS NULL OR TRIM(pickup_code) = ''"
    ).fetchall()
    for row in missing_codes:
        conn.execute(
            "UPDATE reservations SET pickup_code = ? WHERE id = ?",
            (f"MF-{1000 + (int(row['id']) * 7919) % 9000}", row["id"]),
        )

    conn.execute("CREATE INDEX IF NOT EXISTS idx_shops_status ON shops(status)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_inventory_shop_id ON inventory(shop_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_inventory_med_name ON inventory(med_name)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_reservations_inv_status ON reservations(inventory_id, status)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_reservations_phone_status ON reservations(customer_phone, status)")
    conn.commit()


def get_db():
    pg_url = get_active_postgres_url()
    if pg_url:
        if has_app_context():
            conn = getattr(g, "_database", None)
            if conn is None or getattr(g, "_database_key", None) != pg_url:
                if conn is not None:
                    conn.close()
                conn = _connect_postgres(pg_url)
                if pg_url not in _initialized_dbs:
                    ensure_postgres_schema(conn)
                    _initialized_dbs.add(pg_url)
                g._database = conn
                g._database_key = pg_url
            return conn
        conn = _connect_postgres(pg_url)
        if pg_url not in _initialized_dbs:
            ensure_postgres_schema(conn)
            _initialized_dbs.add(pg_url)
        return conn

    db_path = app.config.get("DATABASE") or DEFAULT_DB_PATH
    if has_app_context():
        conn = getattr(g, "_database", None)
        if conn is None or getattr(g, "_database_path", None) != db_path:
            if conn is not None:
                conn.close()
            conn = _connect_sqlite(db_path)
            if db_path not in _initialized_dbs:
                ensure_schema(conn)
                _initialized_dbs.add(db_path)
            g._database = conn
            g._database_path = db_path
        return conn

    conn = _connect_sqlite(db_path)
    if db_path not in _initialized_dbs:
        ensure_schema(conn)
        _initialized_dbs.add(db_path)
    return conn


@app.teardown_appcontext
def close_db_connection(_exception):
    conn = getattr(g, "_database", None)
    if conn is not None:
        conn.close()
        g._database = None


# --- CSRF & SAME-ORIGIN PROTECTION --- #

def get_csrf_token():
    token = session.get("_csrf_token")
    if not token:
        token = secrets.token_hex(16)
        session["_csrf_token"] = token
    return token


app.jinja_env.globals["csrf_token"] = get_csrf_token


@app.before_request
def enforce_request_integrity():
    if request.method not in ("POST", "PUT", "PATCH", "DELETE"):
        return None

    # 1. Reject cross-origin state-mutating requests when Origin header mismatches Host
    origin = request.headers.get("Origin", "").strip()
    if origin:
        parsed_origin = urlparse(origin)
        req_host = (request.host or "").split(",")[0].strip()
        if parsed_origin.netloc and req_host and parsed_origin.netloc.lower() != req_host.lower():
            if request.path.startswith("/api/"):
                return jsonify({"success": False, "error": "Cross-origin request blocked."}), 403
            return Response("Forbidden: Cross-origin request blocked.", status=403)

    # 2. Validate explicit CSRF token when provided via form or X-CSRF-Token header
    submitted_token = (
        request.headers.get("X-CSRF-Token")
        or request.form.get("_csrf_token")
        or ""
    ).strip()
    expected_token = session.get("_csrf_token", "")
    if submitted_token and expected_token and not hmac.compare_digest(submitted_token, expected_token):
        if request.path.startswith("/api/"):
            return jsonify({"success": False, "error": "Invalid or expired security token. Please refresh."}), 403
        return Response("Forbidden: Invalid CSRF token.", status=403)

    return None


@app.after_request
def apply_iframe_and_freshness_headers(response):
    """Ensure Arena's proxied HTTPS preview iframe receives fresh responses and working cookies."""
    if request.is_secure or request.headers.get("X-Forwarded-Proto", "").startswith("https"):
        cookies = response.headers.getlist("Set-Cookie")
        if cookies:
            response.headers.pop("Set-Cookie", None)
            for cookie in cookies:
                if "SameSite=" in cookie:
                    cookie = (
                        cookie.replace("SameSite=Lax", "SameSite=None")
                        .replace("SameSite=Strict", "SameSite=None")
                    )
                else:
                    cookie = f"{cookie}; SameSite=None"
                if "; Secure" not in cookie:
                    cookie = f"{cookie}; Secure"
                response.headers.add("Set-Cookie", cookie)

    if (
        request.path.startswith("/api/")
        or request.path.startswith("/static/js/")
        or request.path.startswith("/static/css/")
        or response.mimetype == "text/html"
    ):
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
    return response


def init_db():
    pg_url = get_active_postgres_url()
    if pg_url:
        with _connect_postgres(pg_url) as conn:
            ensure_postgres_schema(conn)
        _initialized_dbs.add(pg_url)
        return
    db_path = app.config.get("DATABASE") or DEFAULT_DB_PATH
    with _connect_sqlite(db_path) as conn:
        ensure_schema(conn)
    _initialized_dbs.add(db_path)


init_db()


# --- CLINICAL, TIME, & PHONE HELPERS --- #

def normalize_phone_digits(phone):
    digits = "".join(ch for ch in str(phone or "") if ch.isdigit())
    if len(digits) > 10 and digits.startswith("91"):
        return digits[-10:]
    return digits


def generate_pickup_code(db):
    for _ in range(12):
        candidate = f"MF-{random.randint(1000, 9999)}"
        clash = db.execute(
            "SELECT id FROM reservations WHERE pickup_code = ? AND status = 'Pending'",
            (candidate,),
        ).fetchone()
        if not clash:
            return candidate
    return f"MF-{random.randint(1000, 9999)}"


def infer_rx_required(med_name, salt_composition, explicit_flag=0):
    try:
        if int(explicit_flag or 0) == 1:
            return True
    except (TypeError, ValueError):
        pass
    haystack = f"{med_name or ''} {salt_composition or ''}".lower()
    for kw in SCHEDULE_H_SALT_KEYWORDS:
        if kw in haystack:
            return True
    return False


def is_batch_expired(expiry_date_str):
    raw = str(expiry_date_str or "").strip()
    if not raw:
        return False
    today_iso = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    if re.match(r"^\d{4}-\d{2}-\d{2}$", raw):
        return raw < today_iso
    if re.match(r"^\d{4}-\d{2}$", raw):
        return raw < today_iso[:7]
    return False


def _parse_clock_minutes(token):
    m = re.match(r"^\s*(\d{1,2})(?::(\d{2}))?\s*(am|pm)?\s*$", token.strip(), re.IGNORECASE)
    if not m:
        return None
    hour = int(m.group(1))
    minute = int(m.group(2) or 0)
    meridiem = (m.group(3) or "").lower()
    if meridiem == "pm" and hour < 12:
        hour += 12
    elif meridiem == "am" and hour == 12:
        hour = 0
    if 0 <= hour <= 23 and 0 <= minute <= 59:
        return hour * 60 + minute
    return None


def evaluate_shop_open_status(opening_hours, now_ist=None):
    """Return (is_24x7, is_open_now) for a pharmacy opening_hours string."""
    raw = str(opening_hours or "").strip()
    if not raw:
        return False, False

    lower = raw.lower()
    if any(tag in lower for tag in ("24x7", "24/7", "24*7", "24 hours", "24 hrs", "always open")):
        return True, True
    if "closed" in lower and "-" not in lower:
        return False, False

    parts = re.split(r"\s*(?:-|–|—|to)\s*", raw, maxsplit=1, flags=re.IGNORECASE)
    if len(parts) == 2:
        start_m = _parse_clock_minutes(parts[0])
        end_m = _parse_clock_minutes(parts[1])
        if start_m is not None and end_m is not None:
            current = now_ist or datetime.now(IST_OFFSET)
            cur_m = current.hour * 60 + current.minute
            if start_m <= end_m:
                return False, (start_m <= cur_m <= end_m)
            return False, (cur_m >= start_m or cur_m <= end_m)

    return False, True


def extract_normalized_salts(med_name="", salt_composition=""):
    source = str(salt_composition or "").strip()
    if not source:
        # Infer common salt if user only entered a well-known brand/generic word
        lower_name = str(med_name or "").lower()
        for candidate in list(SCHEDULE_H_SALT_KEYWORDS) + ["paracetamol", "aspirin", "ibuprofen", "diclofenac", "cetirizine"]:
            if candidate in lower_name:
                source = candidate
                break
        if "dolo" in lower_name or "crocin" in lower_name or "calpol" in lower_name or "pcm" in lower_name:
            source = "paracetamol"
        elif "ecosprin" in lower_name:
            source = "aspirin"
        elif "augmentin" in lower_name:
            source = "amoxicillin + clavulanic acid"

    tokens = re.split(r"\s*(?:\+|/|&|,|\band\b)\s*", source.lower())
    salts = []
    for tok in tokens:
        cleaned = re.sub(r"\b\d+(?:\.\d+)?\s*(?:mg|mcg|g|ml|iu|%)\b", "", tok)
        cleaned = re.sub(r"\([^)]*\)", "", cleaned)
        cleaned = re.sub(r"\s+", " ", cleaned).strip(" .-_")
        if not cleaned:
            continue
        canonical = SALT_SYNONYMS.get(cleaned, cleaned)
        if canonical and canonical not in salts:
            salts.append(canonical)
    return salts


def analyze_medication_safety(med_items):
    """
    Inspect a list of medicines [{'med_name': ..., 'salt_composition': ...}] for:
      1) Duplicate active salts across distinct brands/entries
      2) Clinically significant drug-class interactions
    """
    normalized_entries = []
    for raw in med_items or []:
        if isinstance(raw, str):
            med_name = raw.strip()
            salt_comp = ""
        elif isinstance(raw, dict):
            med_name = str(raw.get("med_name") or raw.get("name") or "").strip()
            salt_comp = str(raw.get("salt_composition") or raw.get("salt") or "").strip()
        else:
            continue
        if not med_name and not salt_comp:
            continue
        salts = extract_normalized_salts(med_name, salt_comp)
        normalized_entries.append({
            "med_name": med_name or salt_comp.title(),
            "salt_composition": salt_comp,
            "salts": salts,
        })

    warnings = []
    salt_to_meds = {}
    for entry in normalized_entries:
        for salt in entry["salts"]:
            salt_to_meds.setdefault(salt, [])
            if entry["med_name"] not in salt_to_meds[salt]:
                salt_to_meds[salt].append(entry["med_name"])

    for salt, meds in salt_to_meds.items():
        if len(meds) >= 2:
            extra_note = (
                " Combining multiple Paracetamol brands risks accidental liver overdose (max adult daily limit: 4,000 mg)."
                if salt == "paracetamol"
                else " Taking duplicate medicines with the same active ingredient risks accidental double-dosing."
            )
            warnings.append({
                "type": "duplicate_salt",
                "severity": "High",
                "salt": salt.title(),
                "medicines": meds,
                "message": f"Duplicate Active Salt ({salt.title()}): present in {', '.join(meds)}.{extra_note}",
            })

    seen_rule_keys = set()
    for i in range(len(normalized_entries)):
        for j in range(i + 1, len(normalized_entries)):
            a = normalized_entries[i]
            b = normalized_entries[j]
            salts_a = set(a["salts"])
            salts_b = set(b["salts"])
            for group_1, group_2, severity, advice in INTERACTION_RULES:
                matched = (bool(salts_a & group_1) and bool(salts_b & group_2)) or (
                    bool(salts_a & group_2) and bool(salts_b & group_1)
                )
                if not matched:
                    continue
                # Skip self-duplicate rule if it's literally the exact same single salt already flagged above
                if group_1 == group_2 and (salts_a & group_1) == (salts_b & group_2):
                    continue
                pair_names = sorted([a["med_name"], b["med_name"]])
                rule_key = (tuple(pair_names), advice)
                if rule_key not in seen_rule_keys:
                    seen_rule_keys.add(rule_key)
                    warnings.append({
                        "type": "interaction",
                        "severity": severity,
                        "medicines": pair_names,
                        "message": f"{pair_names[0]} + {pair_names[1]}: {advice}",
                    })

    return warnings


def expire_stale_reservations(db):
    db.execute("""
        UPDATE reservations
        SET status = 'Expired'
        WHERE status = 'Pending'
          AND (
              (expires_at IS NOT NULL AND expires_at != '' AND datetime(expires_at) <= datetime('now'))
              OR ((expires_at IS NULL OR expires_at = '') AND created_at IS NOT NULL AND datetime(created_at, '+2 hours') <= datetime('now'))
          )
    """)
    db.commit()


def compute_seconds_remaining(expires_at_val):
    raw = str(expires_at_val or "").strip()
    if not raw:
        return 0
    cleaned = raw.replace("T", " ").split(".")[0].replace("Z", "")
    try:
        exp_dt = datetime.strptime(cleaned, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
        now_dt = datetime.now(timezone.utc)
        return max(0, int((exp_dt - now_dt).total_seconds()))
    except ValueError:
        return 0


def calculate_haversine(lat1, lon1, lat2, lon2):
    if None in (lat1, lon1, lat2, lon2):
        return None
    try:
        lat1, lon1, lat2, lon2 = float(lat1), float(lon1), float(lat2), float(lon2)
    except (TypeError, ValueError):
        return None
    radius_km = 6371.0
    dlat, dlon = math.radians(lat2 - lat1), math.radians(lon2 - lon1)
    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2) ** 2
    )
    return round(radius_km * (2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))), 2)


def is_allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


def save_file(file_obj):
    if not file_obj or not file_obj.filename:
        return None
    safe_name = secure_filename(file_obj.filename)
    if not safe_name or not is_allowed_file(safe_name):
        return None
    os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)
    unique_name = f"{uuid.uuid4().hex[:10]}_{safe_name}"
    filepath = os.path.join(app.config["UPLOAD_FOLDER"], unique_name)
    file_obj.save(filepath)
    return unique_name


def verify_shop_password(stored_password, candidate_password):
    """Verify hashed or legacy plaintext passwords. Returns (matched, needs_rehash)."""
    if not stored_password or not candidate_password:
        return False, False
    looks_hashed = stored_password.startswith(("scrypt:", "pbkdf2:"))
    try:
        if check_password_hash(stored_password, candidate_password):
            return True, False
    except ValueError:
        pass
    if not looks_hashed and stored_password == candidate_password:
        return True, True
    return False, False


# --- PWA & STATIC ROUTES --- #

@app.route("/manifest.json")
def pwa_manifest():
    return send_from_directory(
        os.path.join(app.root_path, "static"),
        "manifest.json",
        mimetype="application/manifest+json",
    )


@app.route("/sw.js")
def pwa_service_worker():
    res = send_from_directory(
        os.path.join(app.root_path, "static"),
        "sw.js",
        mimetype="application/javascript",
    )
    res.headers["Service-Worker-Allowed"] = "/"
    res.headers["Cache-Control"] = "no-store, max-age=0"
    return res


@app.route("/uploads/<path:filename>")
def serve_upload(filename):
    return send_from_directory(app.config["UPLOAD_FOLDER"], filename)


@app.route("/api/health")
def api_health():
    return jsonify({
        "status": "ok",
        "db_engine": "postgresql" if get_active_postgres_url() else "sqlite",
    })


@app.route("/api/csrf-token")
def api_csrf_token():
    return jsonify({"csrf_token": get_csrf_token()})


# --- PUBLIC & LIVE SEARCH API --- #

@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/shops")
def api_shops():
    db = get_db()
    rows = db.execute("""
        SELECT
            s.id,
            s.name,
            s.city,
            s.lat,
            s.lng,
            s.phone,
            s.opening_hours,
            COUNT(i.id) AS medicine_count
        FROM shops s
        LEFT JOIN inventory i ON i.shop_id = s.id
        WHERE s.status = 'Verified' AND s.lat IS NOT NULL AND s.lng IS NOT NULL
        GROUP BY s.id
        ORDER BY s.id DESC
    """).fetchall()
    out = []
    for r in rows:
        d = dict(r)
        is_24x7, is_open_now = evaluate_shop_open_status(d.get("opening_hours"))
        d["is_24x7"] = is_24x7
        d["is_open_now"] = is_open_now
        out.append(d)
    return jsonify(out)


@app.route("/api/autocomplete")
def api_autocomplete():
    q = request.args.get("q", "").strip()
    if len(q) < 1:
        return jsonify([])

    db = get_db()
    expire_stale_reservations(db)
    like_any = f"%{q}%"
    rows = db.execute("""
        SELECT
            i.med_name,
            i.salt_composition,
            i.price,
            i.stock_quantity,
            i.rx_required,
            i.expiry_date,
            s.id AS shop_id,
            COALESCE((
                SELECT SUM(COALESCE(r.quantity, 1))
                FROM reservations r
                WHERE r.inventory_id = i.id AND r.status = 'Pending'
            ), 0) AS active_holds
        FROM inventory i
        JOIN shops s ON s.id = i.shop_id
        WHERE s.status = 'Verified'
          AND (LOWER(i.med_name) LIKE LOWER(?) OR LOWER(i.salt_composition) LIKE LOWER(?))
    """, (like_any, like_any)).fetchall()

    grouped = {}
    q_lower = q.lower()
    for r in rows:
        if is_batch_expired(r["expiry_date"]):
            continue
        med_name = (r["med_name"] or "").strip()
        if not med_name:
            continue
        avail = max(0, int(r["stock_quantity"] or 0) - int(r["active_holds"] or 0))
        key = med_name.lower()
        salt = (r["salt_composition"] or "").strip()
        price = float(r["price"] or 0.0)
        rx = infer_rx_required(med_name, salt, r["rx_required"])

        entry = grouped.get(key)
        if not entry:
            entry = {
                "med_name": med_name,
                "salt_composition": salt,
                "min_price": price if price > 0 else None,
                "store_ids": set(),
                "in_stock_stores": set(),
                "rx_required": rx,
                "starts_with": med_name.lower().startswith(q_lower) or salt.lower().startswith(q_lower),
            }
            grouped[key] = entry
        else:
            if not entry["salt_composition"] and salt:
                entry["salt_composition"] = salt
            if price > 0 and (entry["min_price"] is None or price < entry["min_price"]):
                entry["min_price"] = price
            entry["rx_required"] = entry["rx_required"] or rx

        entry["store_ids"].add(r["shop_id"])
        if avail > 0:
            entry["in_stock_stores"].add(r["shop_id"])

    suggestions = []
    for entry in grouped.values():
        suggestions.append({
            "med_name": entry["med_name"],
            "salt_composition": entry["salt_composition"],
            "min_price": round(entry["min_price"], 2) if entry["min_price"] is not None else 0.0,
            "store_count": len(entry["store_ids"]),
            "in_stock_stores": len(entry["in_stock_stores"]),
            "rx_required": entry["rx_required"],
            "_rank": (0 if entry["starts_with"] else 1, -len(entry["in_stock_stores"]), entry["med_name"].lower()),
        })

    suggestions.sort(key=lambda item: item["_rank"])
    for item in suggestions:
        item.pop("_rank", None)

    return jsonify(suggestions[:8])


@app.route("/api/search")
def api_search():
    query = request.args.get("query", "").strip()
    city = request.args.get("city", "").strip()
    user_lat = request.args.get("lat", type=float)
    user_lng = request.args.get("lng", type=float)
    in_stock_only = request.args.get("in_stock", "").strip().lower() in ("1", "true", "yes")
    open_now_only = request.args.get("open_now", "").strip().lower() in ("1", "true", "yes")
    only_24x7 = request.args.get("only_24x7", "").strip().lower() in ("1", "true", "yes")
    sort_by = request.args.get("sort", "").strip().lower()

    if not query:
        return jsonify([])

    db = get_db()
    expire_stale_reservations(db)

    base_select = """
    SELECT
        s.id AS shop_id,
        s.name AS shop_name,
        s.city,
        s.lat,
        s.lng,
        s.phone AS shop_phone,
        s.opening_hours,
        s.address,
        i.id AS med_id,
        i.id AS id,
        i.med_name,
        i.salt_composition,
        i.price,
        i.stock_quantity,
        i.dosage,
        i.rx_required,
        i.expiry_date,
        COALESCE((
            SELECT SUM(COALESCE(r.quantity, 1))
            FROM reservations r
            WHERE r.inventory_id = i.id AND r.status = 'Pending'
        ), 0) AS active_holds
    FROM inventory i
    JOIN shops s ON s.id = i.shop_id
    WHERE (LOWER(i.med_name) LIKE LOWER(?) OR LOWER(i.salt_composition) LIKE LOWER(?))
      AND s.status = 'Verified'
    """
    search_term = f"%{query}%"
    params = [search_term, search_term]
    sql = base_select

    if city:
        city_parts = [p.strip() for p in city.split(",") if p.strip()]
        if city_parts:
            clauses = " OR ".join(
                ["LOWER(COALESCE(s.city, '')) LIKE LOWER(?) OR LOWER(COALESCE(s.address, '')) LIKE LOWER(?)" for _ in city_parts]
            )
            sql += f" AND ({clauses})"
            for part in city_parts:
                like_val = f"%{part}%"
                params.extend([like_val, like_val])

    rows = db.execute(sql, params).fetchall()

    # If user GPS coordinates are present and Nominatim filled a suburb/locality name
    # (e.g. "Danapur" or "Sri Krishna Puri") while nearby verified shops store "Patna",
    # fall back to verified shops within 25 km of the user's actual coordinates.
    if not rows and city and user_lat is not None and user_lng is not None:
        fallback_rows = db.execute(base_select, [search_term, search_term]).fetchall()
        rows = [
            r for r in fallback_rows
            if (d := calculate_haversine(user_lat, user_lng, r["lat"], r["lng"])) is not None and d <= 25.0
        ]

    results = []
    for r in rows:
        item = dict(r)
        if is_batch_expired(item.get("expiry_date")):
            continue

        stock_qty = int(item.get("stock_quantity") or 0)
        held_qty = int(item.get("active_holds") or 0)
        available_qty = max(0, stock_qty - held_qty)
        item["available_quantity"] = available_qty
        item["distance_km"] = calculate_haversine(user_lat, user_lng, r["lat"], r["lng"])
        item["rx_required"] = infer_rx_required(
            item.get("med_name"),
            item.get("salt_composition"),
            item.get("rx_required"),
        )
        is_24x7, is_open_now = evaluate_shop_open_status(item.get("opening_hours"))
        item["is_24x7"] = is_24x7
        item["is_open_now"] = is_open_now

        if in_stock_only and available_qty <= 0:
            continue
        if only_24x7 and not is_24x7:
            continue
        if open_now_only and not is_open_now:
            continue

        results.append(item)

    if sort_by == "price_asc":
        results.sort(key=lambda x: (float(x.get("price") or 0.0), x["distance_km"] if x["distance_km"] is not None else float("inf")))
    elif sort_by == "stock_desc":
        results.sort(key=lambda x: (-int(x.get("available_quantity") or 0), x["distance_km"] if x["distance_km"] is not None else float("inf")))
    elif user_lat is not None and user_lng is not None:
        results.sort(key=lambda x: x["distance_km"] if x["distance_km"] is not None else float("inf"))

    return jsonify(results)


@app.route("/api/substitutes")
def api_substitutes():
    query = request.args.get("query", "").strip()
    salt = request.args.get("salt", "").strip()
    exclude_name = request.args.get("exclude_med_name", "").strip() or query
    ref_price = request.args.get("ref_price", type=float)
    user_lat = request.args.get("lat", type=float)
    user_lng = request.args.get("lng", type=float)

    db = get_db()
    expire_stale_reservations(db)

    if not salt and query:
        seed = db.execute("""
            SELECT salt_composition, price, med_name
            FROM inventory i
            JOIN shops s ON s.id = i.shop_id
            WHERE s.status = 'Verified'
              AND LOWER(i.med_name) LIKE LOWER(?)
              AND TRIM(COALESCE(i.salt_composition, '')) != ''
            ORDER BY i.price DESC
            LIMIT 1
        """, (f"%{query}%",)).fetchone()
        if seed:
            salt = (seed["salt_composition"] or "").strip()
            if ref_price is None:
                ref_price = float(seed["price"] or 0.0)
            if not exclude_name:
                exclude_name = seed["med_name"] or ""

    salts = extract_normalized_salts(query, salt)
    if not salts:
        return jsonify({"salt": salt, "substitutes": []})

    primary_salt = salts[0]
    rows = db.execute("""
        SELECT
            s.id AS shop_id,
            s.name AS shop_name,
            s.city,
            s.lat,
            s.lng,
            s.phone AS shop_phone,
            s.opening_hours,
            i.id AS med_id,
            i.med_name,
            i.salt_composition,
            i.price,
            i.stock_quantity,
            i.dosage,
            i.rx_required,
            i.expiry_date,
            COALESCE((
                SELECT SUM(COALESCE(r.quantity, 1))
                FROM reservations r
                WHERE r.inventory_id = i.id AND r.status = 'Pending'
            ), 0) AS active_holds
        FROM inventory i
        JOIN shops s ON s.id = i.shop_id
        WHERE s.status = 'Verified'
          AND LOWER(COALESCE(i.salt_composition, '')) LIKE LOWER(?)
    """, (f"%{primary_salt}%",)).fetchall()

    substitutes = []
    excl_lower = exclude_name.lower().strip()
    for r in rows:
        if is_batch_expired(r["expiry_date"]):
            continue
        med_name = (r["med_name"] or "").strip()
        if excl_lower and med_name.lower() == excl_lower:
            continue
        avail = max(0, int(r["stock_quantity"] or 0) - int(r["active_holds"] or 0))
        if avail <= 0:
            continue
        price = float(r["price"] or 0.0)
        savings_amt = 0.0
        savings_pct = 0
        if ref_price and ref_price > 0 and price < ref_price:
            savings_amt = round(ref_price - price, 2)
            savings_pct = int(round((savings_amt / ref_price) * 100))

        is_24x7, is_open_now = evaluate_shop_open_status(r["opening_hours"])
        substitutes.append({
            "med_id": r["med_id"],
            "id": r["med_id"],
            "med_name": med_name,
            "salt_composition": r["salt_composition"],
            "price": price,
            "available_quantity": avail,
            "dosage": r["dosage"] or "",
            "shop_id": r["shop_id"],
            "shop_name": r["shop_name"],
            "city": r["city"],
            "lat": r["lat"],
            "lng": r["lng"],
            "shop_phone": r["shop_phone"] or "",
            "opening_hours": r["opening_hours"] or "",
            "is_24x7": is_24x7,
            "is_open_now": is_open_now,
            "rx_required": infer_rx_required(med_name, r["salt_composition"], r["rx_required"]),
            "distance_km": calculate_haversine(user_lat, user_lng, r["lat"], r["lng"]),
            "savings_amount": savings_amt,
            "savings_pct": savings_pct,
        })

    substitutes.sort(
        key=lambda x: (
            float(x["price"]),
            x["distance_km"] if x["distance_km"] is not None else float("inf"),
        )
    )
    return jsonify({
        "salt": salt or primary_salt.title(),
        "reference_price": ref_price,
        "substitutes": substitutes[:6],
    })


@app.route("/api/safety-check", methods=["POST"])
def api_safety_check():
    data = request.get_json(silent=True) or {}
    raw_items = data.get("items") or []
    db = get_db()

    enriched = []
    for item in raw_items[:20]:
        if isinstance(item, str):
            term = item.strip()
            if not term:
                continue
            row = db.execute(
                "SELECT med_name, salt_composition FROM inventory WHERE LOWER(med_name) LIKE LOWER(?) LIMIT 1",
                (f"%{term}%",),
            ).fetchone()
            if row:
                enriched.append({"med_name": row["med_name"], "salt_composition": row["salt_composition"]})
            else:
                enriched.append({"med_name": term, "salt_composition": ""})
        elif isinstance(item, dict):
            med_name = str(item.get("med_name") or item.get("name") or "").strip()
            salt = str(item.get("salt_composition") or item.get("salt") or "").strip()
            if med_name and not salt:
                row = db.execute(
                    "SELECT salt_composition FROM inventory WHERE LOWER(med_name) LIKE LOWER(?) LIMIT 1",
                    (f"%{med_name}%",),
                ).fetchone()
                if row:
                    salt = row["salt_composition"] or ""
            enriched.append({"med_name": med_name, "salt_composition": salt})

    warnings = analyze_medication_safety(enriched)
    return jsonify({
        "safe": len(warnings) == 0,
        "warnings": warnings,
        "checked_count": len(enriched),
    })


@app.route("/api/prescription-match", methods=["POST"])
def api_prescription_match():
    data = request.get_json(silent=True) or {}
    raw_items = data.get("items") or []
    user_lat = data.get("lat")
    user_lng = data.get("lng")
    try:
        user_lat = float(user_lat) if user_lat is not None else None
        user_lng = float(user_lng) if user_lng is not None else None
    except (TypeError, ValueError):
        user_lat, user_lng = None, None

    requested = []
    seen = set()
    for raw in raw_items[:15]:
        term = (raw.get("name") if isinstance(raw, dict) else str(raw or "")).strip()
        if term and term.lower() not in seen:
            seen.add(term.lower())
            requested.append(term)

    if not requested:
        return jsonify({"success": False, "error": "Add at least one medicine to match."}), 400

    db = get_db()
    expire_stale_reservations(db)

    shops = db.execute("""
        SELECT id, name, city, lat, lng, phone, opening_hours, address
        FROM shops
        WHERE status = 'Verified'
    """).fetchall()

    inv_rows = db.execute("""
        SELECT
            i.id,
            i.shop_id,
            i.med_name,
            i.salt_composition,
            i.price,
            i.stock_quantity,
            i.dosage,
            i.rx_required,
            i.expiry_date,
            COALESCE((
                SELECT SUM(COALESCE(r.quantity, 1))
                FROM reservations r
                WHERE r.inventory_id = i.id AND r.status = 'Pending'
            ), 0) AS active_holds
        FROM inventory i
        JOIN shops s ON s.id = i.shop_id
        WHERE s.status = 'Verified'
    """).fetchall()

    by_shop = {}
    for row in inv_rows:
        if is_batch_expired(row["expiry_date"]):
            continue
        avail = max(0, int(row["stock_quantity"] or 0) - int(row["active_holds"] or 0))
        if avail <= 0:
            continue
        by_shop.setdefault(row["shop_id"], []).append(dict(row, available_quantity=avail))

    # Build clinical safety profile across the requested prescription list
    safety_inputs = []
    for term in requested:
        matched_salt = ""
        matched_label = term
        t_low = term.lower()
        for row in inv_rows:
            if t_low in (row["med_name"] or "").lower() or t_low in (row["salt_composition"] or "").lower():
                matched_label = row["med_name"] or term
                matched_salt = row["salt_composition"] or ""
                break
        safety_inputs.append({"med_name": matched_label, "salt_composition": matched_salt})
    safety_warnings = analyze_medication_safety(safety_inputs)

    ranked_shops = []
    for shop in shops:
        stock_list = by_shop.get(shop["id"], [])
        if not stock_list:
            continue

        matched_items = []
        missing_items = []
        total_price = 0.0

        for term in requested:
            t_low = term.lower()
            candidates = [
                inv for inv in stock_list
                if t_low in (inv["med_name"] or "").lower() or t_low in (inv["salt_composition"] or "").lower()
            ]
            if candidates:
                # Pick lowest-priced matching pack in that pharmacy
                candidates.sort(key=lambda c: float(c.get("price") or 0.0))
                best = candidates[0]
                price_val = float(best.get("price") or 0.0)
                total_price += price_val
                matched_items.append({
                    "requested": term,
                    "med_id": best["id"],
                    "med_name": best["med_name"],
                    "salt_composition": best["salt_composition"] or "",
                    "price": round(price_val, 2),
                    "available_quantity": best["available_quantity"],
                    "rx_required": infer_rx_required(best["med_name"], best["salt_composition"], best["rx_required"]),
                })
            else:
                missing_items.append(term)

        if not matched_items:
            continue

        dist = calculate_haversine(user_lat, user_lng, shop["lat"], shop["lng"])
        is_24x7, is_open_now = evaluate_shop_open_status(shop["opening_hours"])
        ranked_shops.append({
            "shop_id": shop["id"],
            "shop_name": shop["name"],
            "city": shop["city"] or "",
            "lat": shop["lat"],
            "lng": shop["lng"],
            "shop_phone": shop["phone"] or "",
            "opening_hours": shop["opening_hours"] or "",
            "is_24x7": is_24x7,
            "is_open_now": is_open_now,
            "distance_km": dist,
            "matched_count": len(matched_items),
            "requested_count": len(requested),
            "complete_match": len(matched_items) == len(requested),
            "total_price": round(total_price, 2),
            "matched_items": matched_items,
            "missing_items": missing_items,
        })

    ranked_shops.sort(
        key=lambda s: (
            -s["matched_count"],
            s["distance_km"] if s["distance_km"] is not None else float("inf"),
            s["total_price"],
        )
    )

    return jsonify({
        "success": True,
        "requested_items": requested,
        "safety_warnings": safety_warnings,
        "pharmacies": ranked_shops[:10],
    })


@app.route("/api/reserve", methods=["POST"])
def reserve_medicine():
    data = request.get_json(silent=True) or {}
    med_id = data.get("med_id") if data.get("med_id") is not None else data.get("id")
    phone = str(data.get("phone") or "").strip()
    customer_name = str(data.get("customer_name") or "").strip()[:80]
    raw_qty = data.get("quantity", 1)

    try:
        med_id = int(med_id)
    except (TypeError, ValueError):
        return jsonify({"success": False, "error": "Valid medicine selection is required"}), 400

    if not phone:
        return jsonify({"success": False, "error": "Phone number is required"}), 400

    digits_only = "".join(ch for ch in phone if ch.isdigit())
    if len(digits_only) < 7 or len(digits_only) > 15:
        return jsonify({"success": False, "error": "Please enter a valid phone number (7-15 digits)"}), 400

    norm_phone = normalize_phone_digits(phone)

    try:
        quantity = int(raw_qty)
    except (TypeError, ValueError):
        quantity = 1
    if quantity < 1:
        return jsonify({"success": False, "error": "Hold quantity must be at least 1"}), 400
    if quantity > 20:
        return jsonify({"success": False, "error": "Maximum 20 units per online hold"}), 400

    db = get_db()
    expire_stale_reservations(db)

    # Anti-spam active hold cap per normalized phone number
    max_holds = int(app.config.get("MAX_ACTIVE_HOLDS_PER_PHONE", 5))
    pending_for_phone = db.execute("""
        SELECT r.id, r.customer_phone, i.med_name, i.salt_composition
        FROM reservations r
        JOIN inventory i ON i.id = r.inventory_id
        WHERE r.status = 'Pending'
    """).fetchall()
    matching_pending = [
        r for r in pending_for_phone
        if normalize_phone_digits(r["customer_phone"]) == norm_phone
    ]
    if len(matching_pending) >= max_holds:
        return jsonify({
            "success": False,
            "error": f"Active hold limit reached ({max_holds} simultaneous holds per phone number). Cancel or complete an existing hold first.",
        }), 429

    inv_row = db.execute("""
        SELECT
            i.id,
            i.med_name,
            i.salt_composition,
            i.stock_quantity,
            i.rx_required,
            i.expiry_date,
            s.name AS shop_name,
            s.status AS shop_status,
            COALESCE((
                SELECT SUM(COALESCE(r.quantity, 1))
                FROM reservations r
                WHERE r.inventory_id = i.id AND r.status = 'Pending'
            ), 0) AS active_holds
        FROM inventory i
        JOIN shops s ON s.id = i.shop_id
        WHERE i.id = ?
    """, (med_id,)).fetchone()

    if not inv_row or inv_row["shop_status"] != "Verified" or is_batch_expired(inv_row["expiry_date"]):
        return jsonify({"success": False, "error": "Medicine listing is unavailable"}), 404

    available_qty = max(0, int(inv_row["stock_quantity"] or 0) - int(inv_row["active_holds"] or 0))
    if available_qty <= 0:
        return jsonify({"success": False, "error": "Sorry, all units are currently out of stock or on hold"}), 400
    if quantity > available_qty:
        return jsonify({
            "success": False,
            "error": f"Only {available_qty} unit(s) currently available for hold",
        }), 400

    pickup_code = generate_pickup_code(db)
    cur = db.cursor()
    cur.execute("""
        INSERT INTO reservations (
            inventory_id, customer_phone, customer_name, quantity, status, pickup_code, created_at, expires_at
        )
        VALUES (?, ?, ?, ?, 'Pending', ?, datetime('now'), datetime('now', '+2 hours'))
    """, (med_id, phone, customer_name, quantity, pickup_code))
    res_id = cur.lastrowid
    res_row = db.execute("SELECT expires_at FROM reservations WHERE id = ?", (res_id,)).fetchone()
    db.commit()

    # Run clinical safety check across customer's active holds + this newly reserved medicine
    combined_meds = [
        {"med_name": r["med_name"], "salt_composition": r["salt_composition"]}
        for r in matching_pending
    ] + [{"med_name": inv_row["med_name"], "salt_composition": inv_row["salt_composition"]}]
    safety_warnings = analyze_medication_safety(combined_meds)
    rx_req = infer_rx_required(inv_row["med_name"], inv_row["salt_composition"], inv_row["rx_required"])

    remaining_available = max(0, available_qty - quantity)
    return jsonify({
        "success": True,
        "status": "success",
        "message": f"Stock ({quantity} unit{'s' if quantity > 1 else ''}) placed on 2-hour hold at {inv_row['shop_name']}! Pickup Code: {pickup_code}",
        "reservation_id": res_id,
        "pickup_code": pickup_code,
        "quantity": quantity,
        "available_quantity": remaining_available,
        "expires_at": res_row["expires_at"] if res_row else None,
        "rx_required": rx_req,
        "safety_warnings": safety_warnings,
    })


@app.route("/api/my-holds")
def api_my_holds():
    phone = request.args.get("phone", "").strip()
    norm_phone = normalize_phone_digits(phone)
    if len(norm_phone) < 7:
        return jsonify({"success": False, "error": "Enter a valid 7-15 digit phone number.", "holds": []}), 400

    db = get_db()
    expire_stale_reservations(db)

    rows = db.execute("""
        SELECT
            r.id AS reservation_id,
            r.customer_phone,
            r.customer_name,
            COALESCE(r.quantity, 1) AS quantity,
            COALESCE(r.status, 'Pending') AS status,
            r.pickup_code,
            r.created_at,
            r.expires_at,
            i.id AS med_id,
            i.med_name,
            i.salt_composition,
            i.price,
            i.rx_required,
            s.id AS shop_id,
            s.name AS shop_name,
            s.city,
            s.lat,
            s.lng,
            s.phone AS shop_phone,
            s.opening_hours
        FROM reservations r
        JOIN inventory i ON i.id = r.inventory_id
        JOIN shops s ON s.id = i.shop_id
        ORDER BY
            CASE WHEN COALESCE(r.status, 'Pending') = 'Pending' THEN 0 ELSE 1 END,
            r.id DESC
    """).fetchall()

    holds = []
    pending_meds = []
    for r in rows:
        if normalize_phone_digits(r["customer_phone"]) != norm_phone:
            continue
        status = r["status"] or "Pending"
        secs = compute_seconds_remaining(r["expires_at"]) if status == "Pending" else 0
        rx_req = infer_rx_required(r["med_name"], r["salt_composition"], r["rx_required"])
        item = {
            "reservation_id": r["reservation_id"],
            "pickup_code": r["pickup_code"] or f"MF-{1000 + (int(r['reservation_id']) * 7919) % 9000}",
            "customer_name": r["customer_name"] or "",
            "quantity": int(r["quantity"] or 1),
            "status": status,
            "created_at": r["created_at"],
            "expires_at": r["expires_at"],
            "seconds_remaining": secs,
            "med_id": r["med_id"],
            "med_name": r["med_name"],
            "salt_composition": r["salt_composition"] or "",
            "price": float(r["price"] or 0.0),
            "total_price": round(float(r["price"] or 0.0) * int(r["quantity"] or 1), 2),
            "rx_required": rx_req,
            "shop_id": r["shop_id"],
            "shop_name": r["shop_name"],
            "city": r["city"] or "",
            "lat": r["lat"],
            "lng": r["lng"],
            "shop_phone": r["shop_phone"] or "",
            "opening_hours": r["opening_hours"] or "",
        }
        if status == "Pending":
            pending_meds.append({"med_name": r["med_name"], "salt_composition": r["salt_composition"]})
        holds.append(item)

    safety_warnings = analyze_medication_safety(pending_meds)
    active_count = sum(1 for h in holds if h["status"] == "Pending")

    return jsonify({
        "success": True,
        "active_count": active_count,
        "holds": holds[:20],
        "safety_warnings": safety_warnings,
    })


@app.route("/api/my-holds/<int:res_id>/cancel", methods=["POST"])
def api_cancel_my_hold(res_id):
    data = request.get_json(silent=True) or {}
    phone = str(data.get("phone") or "").strip()
    norm_phone = normalize_phone_digits(phone)
    if len(norm_phone) < 7:
        return jsonify({"success": False, "error": "Phone verification required to cancel hold."}), 400

    db = get_db()
    row = db.execute(
        "SELECT id, customer_phone, status FROM reservations WHERE id = ?",
        (res_id,),
    ).fetchone()
    if not row or normalize_phone_digits(row["customer_phone"]) != norm_phone:
        return jsonify({"success": False, "error": "Hold not found for this phone number."}), 404

    if row["status"] != "Pending":
        return jsonify({"success": False, "error": f"Hold is already {row['status']}."}), 400

    db.execute("UPDATE reservations SET status = 'Cancelled' WHERE id = ?", (res_id,))
    db.commit()
    return jsonify({"success": True, "message": "Hold cancelled and units released back to pharmacy inventory."})


# --- AUTHENTICATION & SHOPKEEPER DASHBOARD --- #

@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        password = request.form.get("password", "").strip()
        license_number = request.form.get("license_number", "").strip()
        phone = request.form.get("phone", "").strip()
        opening_hours = request.form.get("opening_hours", "").strip()

        raw_license = request.files.get("license_image")
        raw_gst = request.files.get("gst_certificate")
        raw_photo = request.files.get("shop_photo")

        if raw_gst and raw_gst.filename and not is_allowed_file(raw_gst.filename):
            return render_template("register.html", error="GST certificate must be an image or PDF file.")

        license_file = save_file(raw_license)
        gst_file = save_file(raw_gst)
        photo_file = save_file(raw_photo)

        if name and password and license_number and license_file and photo_file:
            db = get_db()
            existing = db.execute("SELECT id FROM shops WHERE LOWER(name) = LOWER(?)", (name,)).fetchone()
            if existing:
                return render_template("register.html", error="Shop name already registered.")

            hashed_pw = generate_password_hash(password)
            try:
                cur = db.cursor()
                cur.execute("""
                    INSERT INTO shops (
                        name, password, license_number, license_image, gst_certificate,
                        shop_photo, phone, opening_hours, status
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'Pending')
                """, (name, hashed_pw, license_number, license_file, gst_file, photo_file, phone, opening_hours))
                db.commit()
                session["shop_id"] = cur.lastrowid
                return redirect("/dashboard")
            except Exception:
                return render_template("register.html", error="Shop name already registered.")

        return render_template(
            "register.html",
            error="Please fill in all required fields and upload valid image files (.png, .jpg, .jpeg, .webp).",
        )

    return render_template("register.html")


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "").strip()

        db = get_db()
        candidates = db.execute("SELECT * FROM shops WHERE name = ? ORDER BY id DESC", (username,)).fetchall()
        if not candidates:
            candidates = db.execute(
                "SELECT * FROM shops WHERE LOWER(name) = LOWER(?) ORDER BY id DESC",
                (username,),
            ).fetchall()

        for shop in candidates:
            pw_matches, needs_rehash = verify_shop_password(shop["password"], password)
            if pw_matches:
                if needs_rehash:
                    db.execute(
                        "UPDATE shops SET password = ? WHERE id = ?",
                        (generate_password_hash(password), shop["id"]),
                    )
                    db.commit()
                session["shop_id"] = shop["id"]
                return redirect("/dashboard")

        return render_template("login.html", error="Invalid Shop Name or Password.")

    return render_template("login.html")


@app.route("/logout")
def logout():
    session.pop("shop_id", None)
    return redirect("/")


def _compute_dashboard_kpis(items, reservations):
    total_skus = len(items)
    low_stock_count = 0
    expired_count = 0
    for item in items:
        avail = max(0, int(item["stock_quantity"] or 0) - int(item["active_holds"] or 0))
        if avail <= 5:
            low_stock_count += 1
        if is_batch_expired(item["expiry_date"]):
            expired_count += 1

    active_holds_count = sum(1 for r in reservations if (r["status"] or "Pending") == "Pending")
    completed_count = sum(1 for r in reservations if r["status"] == "Completed")
    return {
        "total_skus": total_skus,
        "low_stock_count": low_stock_count,
        "expired_count": expired_count,
        "active_holds_count": active_holds_count,
        "completed_count": completed_count,
    }


@app.route("/dashboard", methods=["GET", "POST"])
def dashboard():
    if "shop_id" not in session:
        return redirect("/login")

    db = get_db()
    shop = db.execute("SELECT * FROM shops WHERE id = ?", (session["shop_id"],)).fetchone()
    if not shop:
        session.pop("shop_id", None)
        return redirect("/login")

    expire_stale_reservations(db)

    if request.method == "POST":
        med_name = request.form.get("med_name", "").strip()
        salt_composition = request.form.get("salt_composition", "").strip()
        price = max(0.0, request.form.get("price", type=float, default=0.0))
        stock_quantity = max(0, request.form.get("stock_quantity", type=int, default=1))
        dosage = request.form.get("dosage", "").strip()
        expiry_date = request.form.get("expiry_date", "").strip()[:10]
        rx_flag = 1 if request.form.get("rx_required") in ("1", "on", "true", "yes") else 0
        if not rx_flag and infer_rx_required(med_name, salt_composition, 0):
            rx_flag = 1

        if med_name:
            db.execute("""
                INSERT INTO inventory (
                    shop_id, med_name, salt_composition, price, stock_quantity, dosage, rx_required, expiry_date
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (session["shop_id"], med_name, salt_composition, price, stock_quantity, dosage, rx_flag, expiry_date))
            db.commit()
            return redirect("/dashboard")

    raw_items = db.execute("""
        SELECT
            i.*,
            COALESCE((
                SELECT SUM(COALESCE(r.quantity, 1))
                FROM reservations r
                WHERE r.inventory_id = i.id AND r.status = 'Pending'
            ), 0) AS active_holds
        FROM inventory i
        WHERE i.shop_id = ?
        ORDER BY i.id DESC
    """, (session["shop_id"],)).fetchall()

    items = []
    for row in raw_items:
        d = dict(row)
        d["is_expired"] = is_batch_expired(d.get("expiry_date"))
        d["rx_effective"] = infer_rx_required(d.get("med_name"), d.get("salt_composition"), d.get("rx_required"))
        items.append(d)

    reservations = db.execute("""
        SELECT
            r.id,
            r.customer_phone,
            r.customer_name,
            COALESCE(r.quantity, 1) AS quantity,
            COALESCE(r.status, 'Pending') AS status,
            r.pickup_code,
            r.created_at,
            r.expires_at,
            i.med_name
        FROM reservations r
        JOIN inventory i ON r.inventory_id = i.id
        WHERE i.shop_id = ?
        ORDER BY
            CASE WHEN COALESCE(r.status, 'Pending') = 'Pending' THEN 0 ELSE 1 END,
            r.id DESC
    """, (session["shop_id"],)).fetchall()

    kpi = _compute_dashboard_kpis(items, reservations)
    csv_notice = session.pop("csv_notice", None)

    return render_template(
        "dashboard.html",
        items=items,
        shop=shop,
        reservations=reservations,
        kpi=kpi,
        csv_notice=csv_notice,
    )


@app.route("/api/dashboard/summary")
def api_dashboard_summary():
    if "shop_id" not in session:
        return jsonify({"authenticated": False}), 401

    db = get_db()
    expire_stale_reservations(db)
    raw_items = db.execute("""
        SELECT
            i.*,
            COALESCE((
                SELECT SUM(COALESCE(r.quantity, 1))
                FROM reservations r
                WHERE r.inventory_id = i.id AND r.status = 'Pending'
            ), 0) AS active_holds
        FROM inventory i
        WHERE i.shop_id = ?
    """, (session["shop_id"],)).fetchall()
    items = [dict(r) for r in raw_items]

    reservations = db.execute("""
        SELECT
            r.id,
            r.customer_phone,
            r.customer_name,
            COALESCE(r.quantity, 1) AS quantity,
            COALESCE(r.status, 'Pending') AS status,
            r.pickup_code,
            r.created_at,
            r.expires_at,
            i.med_name
        FROM reservations r
        JOIN inventory i ON r.inventory_id = i.id
        WHERE i.shop_id = ?
        ORDER BY
            CASE WHEN COALESCE(r.status, 'Pending') = 'Pending' THEN 0 ELSE 1 END,
            r.id DESC
        LIMIT 25
    """, (session["shop_id"],)).fetchall()

    kpi = _compute_dashboard_kpis(items, reservations)
    pending_list = []
    for r in reservations:
        if (r["status"] or "Pending") == "Pending":
            pending_list.append({
                "id": r["id"],
                "med_name": r["med_name"],
                "quantity": int(r["quantity"] or 1),
                "customer_name": r["customer_name"] or "",
                "customer_phone": r["customer_phone"] or "",
                "pickup_code": r["pickup_code"] or f"MF-{1000 + (int(r['id']) * 7919) % 9000}",
                "expires_at": r["expires_at"] or "",
            })

    return jsonify({
        "authenticated": True,
        "kpi": kpi,
        "pending_holds": pending_list,
    })


@app.route("/inventory/<int:med_id>/adjust_stock", methods=["POST"])
def adjust_medicine_stock(med_id):
    if "shop_id" not in session:
        if request.is_json or request.headers.get("Accept") == "application/json":
            return jsonify({"ok": False, "error": "Authentication required"}), 401
        return redirect("/login")

    payload = request.get_json(silent=True) or {}
    raw_delta = payload.get("delta") if "delta" in payload else request.form.get("delta", "0")
    try:
        delta = int(raw_delta)
    except (TypeError, ValueError):
        delta = 0

    db = get_db()
    row = db.execute("""
        SELECT
            i.id,
            i.stock_quantity,
            COALESCE((
                SELECT SUM(COALESCE(r.quantity, 1))
                FROM reservations r
                WHERE r.inventory_id = i.id AND r.status = 'Pending'
            ), 0) AS active_holds
        FROM inventory i
        WHERE i.id = ? AND i.shop_id = ?
    """, (med_id, session["shop_id"])).fetchone()

    if not row:
        if request.is_json or request.headers.get("Accept") == "application/json":
            return jsonify({"ok": False, "error": "Medicine not found"}), 404
        return redirect("/dashboard")

    new_stock = max(0, int(row["stock_quantity"] or 0) + delta)
    db.execute(
        "UPDATE inventory SET stock_quantity = ? WHERE id = ? AND shop_id = ?",
        (new_stock, med_id, session["shop_id"]),
    )
    db.commit()

    avail = max(0, new_stock - int(row["active_holds"] or 0))
    if request.is_json or "application/json" in (request.headers.get("Accept") or ""):
        return jsonify({
            "ok": True,
            "med_id": med_id,
            "stock_quantity": new_stock,
            "active_holds": int(row["active_holds"] or 0),
            "available_quantity": avail,
            "low_stock": avail <= 5,
        })
    return redirect("/dashboard")


@app.route("/dashboard/export_csv")
def export_inventory_csv():
    if "shop_id" not in session:
        return redirect("/login")

    db = get_db()
    rows = db.execute("""
        SELECT med_name, salt_composition, dosage, price, stock_quantity, rx_required, expiry_date
        FROM inventory
        WHERE shop_id = ?
        ORDER BY med_name ASC
    """, (session["shop_id"],)).fetchall()

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow([
        "med_name",
        "salt_composition",
        "dosage",
        "price",
        "stock_quantity",
        "rx_required",
        "expiry_date",
    ])
    for r in rows:
        writer.writerow([
            r["med_name"] or "",
            r["salt_composition"] or "",
            r["dosage"] or "",
            r["price"] if r["price"] is not None else 0.0,
            r["stock_quantity"] if r["stock_quantity"] is not None else 0,
            1 if infer_rx_required(r["med_name"], r["salt_composition"], r["rx_required"]) else 0,
            r["expiry_date"] or "",
        ])

    return Response(
        buf.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename=medfinder_inventory.csv"},
    )


@app.route("/dashboard/import_csv", methods=["POST"])
def import_inventory_csv():
    if "shop_id" not in session:
        return redirect("/login")

    upload = request.files.get("csv_file")
    if not upload or not upload.filename:
        session["csv_notice"] = "Please choose a .csv file to upload."
        return redirect("/dashboard")

    try:
        raw_text = upload.stream.read().decode("utf-8-sig", errors="replace")
    except Exception:
        session["csv_notice"] = "Could not read CSV file encoding."
        return redirect("/dashboard")

    reader = csv.DictReader(io.StringIO(raw_text))
    db = get_db()
    inserted = 0
    updated = 0

    for row in reader:
        norm = {(k or "").strip().lower(): (v or "").strip() for k, v in row.items()}
        med_name = norm.get("med_name") or norm.get("medicine") or norm.get("name") or ""
        if not med_name:
            continue
        salt = norm.get("salt_composition") or norm.get("salt") or norm.get("generic") or ""
        dosage = norm.get("dosage") or ""
        try:
            price = max(0.0, float(norm.get("price") or 0.0))
        except ValueError:
            price = 0.0
        try:
            stock_qty = max(0, int(float(norm.get("stock_quantity") or norm.get("stock") or 0)))
        except ValueError:
            stock_qty = 0
        rx_raw = (norm.get("rx_required") or norm.get("rx") or "").lower()
        rx_flag = 1 if rx_raw in ("1", "true", "yes", "y", "rx", "h") else 0
        if not rx_flag and infer_rx_required(med_name, salt, 0):
            rx_flag = 1
        expiry_date = (norm.get("expiry_date") or norm.get("expiry") or "")[:10]

        existing = db.execute(
            "SELECT id FROM inventory WHERE shop_id = ? AND LOWER(med_name) = LOWER(?)",
            (session["shop_id"], med_name),
        ).fetchone()
        if existing:
            db.execute("""
                UPDATE inventory
                SET salt_composition = ?, dosage = ?, price = ?, stock_quantity = ?, rx_required = ?, expiry_date = ?
                WHERE id = ? AND shop_id = ?
            """, (salt, dosage, price, stock_qty, rx_flag, expiry_date, existing["id"], session["shop_id"]))
            updated += 1
        else:
            db.execute("""
                INSERT INTO inventory (
                    shop_id, med_name, salt_composition, price, stock_quantity, dosage, rx_required, expiry_date
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (session["shop_id"], med_name, salt, price, stock_qty, dosage, rx_flag, expiry_date))
            inserted += 1

    db.commit()
    session["csv_notice"] = f"CSV sync complete: {inserted} added, {updated} updated."
    return redirect("/dashboard")


@app.route("/update_location", methods=["POST"])
def update_location():
    if "shop_id" not in session:
        return redirect("/login")

    db = get_db()
    shop = db.execute("SELECT * FROM shops WHERE id = ?", (session["shop_id"],)).fetchone()
    if not shop:
        session.pop("shop_id", None)
        return redirect("/login")

    raw_lat = request.form.get("lat", "").strip()
    raw_lng = request.form.get("lng", "").strip()
    city = request.form.get("city", "").strip() or (shop["city"] or "")
    phone = request.form.get("phone", shop["phone"] or "").strip()
    opening_hours = request.form.get("opening_hours", shop["opening_hours"] or "").strip()

    lat_val = shop["lat"]
    lng_val = shop["lng"]
    if raw_lat and raw_lng:
        try:
            parsed_lat = float(raw_lat)
            parsed_lng = float(raw_lng)
            if -90.0 <= parsed_lat <= 90.0 and -180.0 <= parsed_lng <= 180.0:
                lat_val = parsed_lat
                lng_val = parsed_lng
        except ValueError:
            pass

    db.execute(
        "UPDATE shops SET lat = ?, lng = ?, city = ?, phone = ?, opening_hours = ? WHERE id = ?",
        (lat_val, lng_val, city, phone, opening_hours, session["shop_id"]),
    )
    db.commit()
    return redirect("/dashboard")


@app.route("/update_medicine/<int:med_id>", methods=["POST"])
def update_medicine(med_id):
    if "shop_id" not in session:
        return redirect("/login")

    med_name = request.form.get("med_name", "").strip()
    salt_composition = request.form.get("salt_composition", "").strip()
    dosage = request.form.get("dosage", "").strip()
    price = max(0.0, request.form.get("price", type=float, default=0.0))
    stock_quantity = max(0, request.form.get("stock_quantity", type=int, default=0))
    expiry_date = request.form.get("expiry_date", "").strip()[:10]
    has_rx_field = "rx_required" in request.form or "rx_present" in request.form
    rx_flag = 1 if request.form.get("rx_required") in ("1", "on", "true", "yes") else 0

    db = get_db()
    if med_name:
        if has_rx_field:
            db.execute("""
                UPDATE inventory
                SET med_name = ?, salt_composition = ?, dosage = ?, price = ?, stock_quantity = ?,
                    rx_required = ?, expiry_date = ?
                WHERE id = ? AND shop_id = ?
            """, (med_name, salt_composition, dosage, price, stock_quantity, rx_flag, expiry_date, med_id, session["shop_id"]))
        else:
            db.execute("""
                UPDATE inventory
                SET med_name = ?, salt_composition = ?, dosage = ?, price = ?, stock_quantity = ?
                WHERE id = ? AND shop_id = ?
            """, (med_name, salt_composition, dosage, price, stock_quantity, med_id, session["shop_id"]))
    else:
        db.execute("""
            UPDATE inventory
            SET price = ?, stock_quantity = ?
            WHERE id = ? AND shop_id = ?
        """, (price, stock_quantity, med_id, session["shop_id"]))
    db.commit()
    return redirect("/dashboard")


@app.route("/delete_medicine/<int:med_id>", methods=["POST"])
def delete_medicine(med_id):
    if "shop_id" not in session:
        return redirect("/login")

    db = get_db()
    db.execute("DELETE FROM inventory WHERE id = ? AND shop_id = ?", (med_id, session["shop_id"]))
    db.commit()
    return redirect("/dashboard")


@app.route("/reservation/<int:res_id>/<action>", methods=["POST"])
def update_reservation_status(res_id, action):
    if "shop_id" not in session:
        return redirect("/login")

    if action not in ("complete", "cancel"):
        return redirect("/dashboard")

    db = get_db()
    res_row = db.execute("""
        SELECT r.id, r.inventory_id, COALESCE(r.quantity, 1) AS quantity, COALESCE(r.status, 'Pending') AS status
        FROM reservations r
        JOIN inventory i ON r.inventory_id = i.id
        WHERE r.id = ? AND i.shop_id = ?
    """, (res_id, session["shop_id"])).fetchone()

    if res_row and res_row["status"] == "Pending":
        if action == "complete":
            db.execute(
                "UPDATE inventory SET stock_quantity = MAX(0, COALESCE(stock_quantity, 0) - ?) WHERE id = ?",
                (res_row["quantity"], res_row["inventory_id"]),
            )
            db.execute("UPDATE reservations SET status = 'Completed' WHERE id = ?", (res_id,))
        elif action == "cancel":
            db.execute("UPDATE reservations SET status = 'Cancelled' WHERE id = ?", (res_id,))
        db.commit()

    return redirect("/dashboard")


# --- ADMIN ROUTING --- #

@app.route("/admin", methods=["GET", "POST"])
def admin():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "").strip()

        if username == ADMIN_USERNAME and check_password_hash(ADMIN_PASSWORD_HASH, password):
            session["admin"] = True
            return redirect("/admin/dashboard")

        return render_template("admin.html", error="Invalid admin credentials.")

    return render_template("admin.html")


@app.route("/admin/dashboard")
def admin_dashboard():
    if not session.get("admin"):
        return redirect("/admin")

    db = get_db()
    pending = db.execute("SELECT * FROM shops WHERE status = 'Pending' ORDER BY id DESC").fetchall()
    verified = db.execute("SELECT * FROM shops WHERE status = 'Verified' ORDER BY id DESC").fetchall()
    rejected = db.execute("SELECT * FROM shops WHERE status = 'Rejected' ORDER BY id DESC").fetchall()

    upload_dir = app.config["UPLOAD_FOLDER"]
    existing_uploads = set(os.listdir(upload_dir)) if os.path.isdir(upload_dir) else set()

    return render_template(
        "admin_dashboard.html",
        pending=pending,
        verified=verified,
        rejected=rejected,
        existing_uploads=existing_uploads,
    )


@app.route("/approve/<int:shop_id>", methods=["GET", "POST"])
def approve(shop_id):
    if not session.get("admin"):
        return redirect("/admin")
    db = get_db()
    db.execute("UPDATE shops SET status = 'Verified' WHERE id = ?", (shop_id,))
    db.commit()
    return redirect("/admin/dashboard")


@app.route("/reject/<int:shop_id>", methods=["GET", "POST"])
def reject(shop_id):
    if not session.get("admin"):
        return redirect("/admin")
    db = get_db()
    db.execute("UPDATE shops SET status = 'Rejected' WHERE id = ?", (shop_id,))
    db.commit()
    return redirect("/admin/dashboard")


@app.route("/pending/<int:shop_id>", methods=["GET", "POST"])
def mark_pending(shop_id):
    if not session.get("admin"):
        return redirect("/admin")
    db = get_db()
    db.execute("UPDATE shops SET status = 'Pending' WHERE id = ?", (shop_id,))
    db.commit()
    return redirect("/admin/dashboard")


@app.route("/admin/logout")
def admin_logout():
    session.pop("admin", None)
    return redirect("/admin")


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)), debug=True)
