import math
import os
import sqlite3
import uuid
from flask import (
    Flask,
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
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "webp", "gif", "pdf"}

ADMIN_USERNAME = os.environ.get("ADMIN_USER", "admin")
ADMIN_PASSWORD_HASH = generate_password_hash(os.environ.get("ADMIN_PASS", "admin123"))

_initialized_dbs = set()


def _connect_sqlite(db_path):
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn


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
        stock_quantity INTEGER DEFAULT 1,
        dosage TEXT DEFAULT '',
        FOREIGN KEY (shop_id) REFERENCES shops (id) ON DELETE CASCADE
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
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        expires_at TEXT,
        FOREIGN KEY (inventory_id) REFERENCES inventory (id) ON DELETE CASCADE
    )
    """)

    # Non-destructive additive schema migrations for existing database.db files
    cols_shops = {c[1] for c in conn.execute("PRAGMA table_info(shops)")}
    shop_migrations = [
        ("status", "TEXT DEFAULT 'Pending'"),
        ("license_number", "TEXT"),
        ("license_image", "TEXT"),
        ("gst_certificate", "TEXT"),
        ("shop_photo", "TEXT"),
        ("phone", "TEXT DEFAULT ''"),
        ("opening_hours", "TEXT DEFAULT ''"),
        ("address", "TEXT DEFAULT ''"),
        ("created_at", "TEXT"),
    ]
    for col_name, col_def in shop_migrations:
        if col_name not in cols_shops:
            conn.execute(f"ALTER TABLE shops ADD COLUMN {col_name} {col_def}")

    cols_inv = {c[1] for c in conn.execute("PRAGMA table_info(inventory)")}
    inv_migrations = [
        ("price", "REAL DEFAULT 0.0"),
        ("stock_quantity", "INTEGER DEFAULT 1"),
        ("dosage", "TEXT DEFAULT ''"),
        ("salt_composition", "TEXT DEFAULT ''"),
    ]
    for col_name, col_def in inv_migrations:
        if col_name not in cols_inv:
            conn.execute(f"ALTER TABLE inventory ADD COLUMN {col_name} {col_def}")

    cols_res = {c[1] for c in conn.execute("PRAGMA table_info(reservations)")}
    res_migrations = [
        ("customer_name", "TEXT DEFAULT ''"),
        ("quantity", "INTEGER DEFAULT 1"),
        ("status", "TEXT DEFAULT 'Pending'"),
        ("created_at", "TEXT"),
        ("expires_at", "TEXT"),
    ]
    for col_name, col_def in res_migrations:
        if col_name not in cols_res:
            conn.execute(f"ALTER TABLE reservations ADD COLUMN {col_name} {col_def}")

    conn.commit()


def get_db():
    db_path = app.config.get("DATABASE") or DEFAULT_DB_PATH
    if has_app_context():
        conn = g.get("_db_conn")
        if conn is None or g.get("_db_path") != db_path:
            if conn is not None:
                conn.close()
            conn = _connect_sqlite(db_path)
            if db_path not in _initialized_dbs:
                ensure_schema(conn)
                _initialized_dbs.add(db_path)
            g._db_conn = conn
            g._db_path = db_path
        return conn

    conn = _connect_sqlite(db_path)
    if db_path not in _initialized_dbs:
        ensure_schema(conn)
        _initialized_dbs.add(db_path)
    return conn


@app.teardown_appcontext
def close_db(_exc=None):
    conn = g.pop("_db_conn", None)
    g.pop("_db_path", None)
    if conn is not None:
        conn.close()


@app.before_request
def configure_preview_cookies():
    host = (request.headers.get("X-Forwarded-Host") or request.host or "").lower()
    proto = (request.headers.get("X-Forwarded-Proto") or request.scheme or "").split(",")[0].lower()
    is_https_preview = proto == "https" or ".e2b.app" in host or host.endswith(".arena.ai")
    app.config["SESSION_COOKIE_SAMESITE"] = "None" if is_https_preview else "Lax"
    app.config["SESSION_COOKIE_SECURE"] = bool(is_https_preview)
    if "SESSION_COOKIE_PARTITIONED" in app.config:
        app.config["SESSION_COOKIE_PARTITIONED"] = bool(is_https_preview)


@app.after_request
def add_fresh_asset_headers(response):
    response.headers.setdefault("Permissions-Policy", "geolocation=*")
    ctype = (response.headers.get("Content-Type") or "").lower()
    if any(t in ctype for t in ("text/html", "javascript", "text/css", "application/json")):
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        response.headers["Pragma"] = "no-cache"
    return response


def init_db():
    db_path = app.config.get("DATABASE") or DEFAULT_DB_PATH
    with _connect_sqlite(db_path) as conn:
        ensure_schema(conn)
    _initialized_dbs.add(db_path)


init_db()


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


@app.route("/uploads/<path:filename>")
def serve_upload(filename):
    return send_from_directory(app.config["UPLOAD_FOLDER"], filename)


@app.route("/api/health")
def api_health():
    return jsonify({"status": "ok"})


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
    return jsonify([dict(r) for r in rows])


@app.route("/api/search")
def api_search():
    query = request.args.get("query", "").strip()
    city = request.args.get("city", "").strip()
    user_lat = request.args.get("lat", type=float)
    user_lng = request.args.get("lng", type=float)
    in_stock_only = request.args.get("in_stock", "").strip().lower() in ("1", "true", "yes")
    sort_by = request.args.get("sort", "").strip().lower()

    if not query:
        return jsonify([])

    db = get_db()
    expire_stale_reservations(db)

    # Case-insensitive search across Medicine Name and Salt Composition
    sql = """
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
        fallback_rows = db.execute(
            """
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
                COALESCE((
                    SELECT SUM(COALESCE(r.quantity, 1))
                    FROM reservations r
                    WHERE r.inventory_id = i.id AND r.status = 'Pending'
                ), 0) AS active_holds
            FROM inventory i
            JOIN shops s ON s.id = i.shop_id
            WHERE (LOWER(i.med_name) LIKE LOWER(?) OR LOWER(i.salt_composition) LIKE LOWER(?))
              AND s.status = 'Verified'
            """,
            [search_term, search_term],
        ).fetchall()
        rows = [
            r for r in fallback_rows
            if (d := calculate_haversine(user_lat, user_lng, r["lat"], r["lng"])) is not None and d <= 25.0
        ]

    results = []

    for r in rows:
        item = dict(r)
        stock_qty = int(item.get("stock_quantity") or 0)
        held_qty = int(item.get("active_holds") or 0)
        available_qty = max(0, stock_qty - held_qty)
        item["available_quantity"] = available_qty
        item["distance_km"] = calculate_haversine(user_lat, user_lng, r["lat"], r["lng"])

        if in_stock_only and available_qty <= 0:
            continue

        results.append(item)

    if sort_by == "price_asc":
        results.sort(key=lambda x: (float(x.get("price") or 0.0), x["distance_km"] if x["distance_km"] is not None else float("inf")))
    elif sort_by == "stock_desc":
        results.sort(key=lambda x: (-int(x.get("available_quantity") or 0), x["distance_km"] if x["distance_km"] is not None else float("inf")))
    elif user_lat is not None and user_lng is not None:
        results.sort(key=lambda x: x["distance_km"] if x["distance_km"] is not None else float("inf"))

    return jsonify(results)


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

    try:
        quantity = int(raw_qty)
    except (TypeError, ValueError):
        quantity = 1
    if quantity < 1:
        return jsonify({"success": False, "error": "Hold quantity must be at least 1"}), 400

    db = get_db()
    expire_stale_reservations(db)

    inv_row = db.execute("""
        SELECT
            i.id,
            i.med_name,
            i.stock_quantity,
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

    if not inv_row or inv_row["shop_status"] != "Verified":
        return jsonify({"success": False, "error": "Medicine listing is unavailable"}), 404

    available_qty = max(0, int(inv_row["stock_quantity"] or 0) - int(inv_row["active_holds"] or 0))
    if available_qty <= 0:
        return jsonify({"success": False, "error": "Sorry, all units are currently out of stock or on hold"}), 400
    if quantity > available_qty:
        return jsonify({
            "success": False,
            "error": f"Only {available_qty} unit(s) currently available for hold",
        }), 400

    cur = db.cursor()
    cur.execute("""
        INSERT INTO reservations (inventory_id, customer_phone, customer_name, quantity, status, created_at, expires_at)
        VALUES (?, ?, ?, ?, 'Pending', datetime('now'), datetime('now', '+2 hours'))
    """, (med_id, phone, customer_name, quantity))
    res_id = cur.lastrowid
    res_row = db.execute("SELECT expires_at FROM reservations WHERE id = ?", (res_id,)).fetchone()
    db.commit()

    remaining_available = max(0, available_qty - quantity)
    return jsonify({
        "success": True,
        "status": "success",
        "message": f"Stock ({quantity} unit{'s' if quantity > 1 else ''}) placed on 2-hour hold at {inv_row['shop_name']}!",
        "reservation_id": res_id,
        "quantity": quantity,
        "available_quantity": remaining_available,
        "expires_at": res_row["expires_at"] if res_row else None,
    })


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
            except sqlite3.IntegrityError:
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

        if med_name:
            db.execute("""
                INSERT INTO inventory (shop_id, med_name, salt_composition, price, stock_quantity, dosage)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (session["shop_id"], med_name, salt_composition, price, stock_quantity, dosage))
            db.commit()
            return redirect("/dashboard")

    items = db.execute("""
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

    reservations = db.execute("""
        SELECT
            r.id,
            r.customer_phone,
            r.customer_name,
            COALESCE(r.quantity, 1) AS quantity,
            COALESCE(r.status, 'Pending') AS status,
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

    return render_template("dashboard.html", items=items, shop=shop, reservations=reservations)


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

    db = get_db()
    if med_name:
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
