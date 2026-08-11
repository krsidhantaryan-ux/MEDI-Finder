import os
import math
import sqlite3
from flask import Flask, render_template, request, redirect, session, jsonify, send_from_directory
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "medfinder_secure_production_key_2026")

UPLOAD_FOLDER = os.path.join(app.root_path, "static", "uploads")
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER
app.config["MAX_CONTENT_LENGTH"] = 16 * 1024 * 1024
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

ADMIN_USERNAME = os.environ.get("ADMIN_USER", "admin")
ADMIN_PASSWORD_HASH = generate_password_hash(os.environ.get("ADMIN_PASS", "admin123"))

def get_db():
    conn = sqlite3.connect("database.db")
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn

def init_db():
    with get_db() as conn:
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
            status TEXT DEFAULT 'Pending',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (inventory_id) REFERENCES inventory (id) ON DELETE CASCADE
        )
        """)

        # Database Schema Migrations
        cols_shops = [c[1] for c in conn.execute("PRAGMA table_info(shops)")]
        if "status" not in cols_shops:
            conn.execute("ALTER TABLE shops ADD COLUMN status TEXT DEFAULT 'Pending'")
        if "license_number" not in cols_shops:
            conn.execute("ALTER TABLE shops ADD COLUMN license_number TEXT")
        if "license_image" not in cols_shops:
            conn.execute("ALTER TABLE shops ADD COLUMN license_image TEXT")
        if "gst_certificate" not in cols_shops:
            conn.execute("ALTER TABLE shops ADD COLUMN gst_certificate TEXT")
        if "shop_photo" not in cols_shops:
            conn.execute("ALTER TABLE shops ADD COLUMN shop_photo TEXT")

        cols_inv = [c[1] for c in conn.execute("PRAGMA table_info(inventory)")]
        if "price" not in cols_inv:
            conn.execute("ALTER TABLE inventory ADD COLUMN price REAL DEFAULT 0.0")
        if "stock_quantity" not in cols_inv:
            conn.execute("ALTER TABLE inventory ADD COLUMN stock_quantity INTEGER DEFAULT 1")
        if "dosage" not in cols_inv:
            conn.execute("ALTER TABLE inventory ADD COLUMN dosage TEXT DEFAULT ''")
        if "salt_composition" not in cols_inv:
            conn.execute("ALTER TABLE inventory ADD COLUMN salt_composition TEXT DEFAULT ''")

        conn.commit()

init_db()

def calculate_haversine(lat1, lon1, lat2, lon2):
    if None in (lat1, lon1, lat2, lon2):
        return None
    R = 6371.0 # Radius of Earth in kilometers
    dlat, dlon = math.radians(lat2 - lat1), math.radians(lon2 - lon1)
    a = math.sin(dlat / 2)**2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon / 2)**2
    return round(R * (2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))), 2)

def save_file(file_obj):
    if file_obj and file_obj.filename != "":
        filename = secure_filename(file_obj.filename)
        filepath = os.path.join(app.config["UPLOAD_FOLDER"], filename)
        file_obj.save(filepath)
        return filename
    return None

@app.route("/uploads/<path:filename>")
def serve_upload(filename):
    return send_from_directory(app.config["UPLOAD_FOLDER"], filename)

# --- PUBLIC & LIVE SEARCH API --- #

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/api/search")
def api_search():
    query = request.args.get("query", "").strip()
    city = request.args.get("city", "").strip()
    user_lat = request.args.get("lat", type=float)
    user_lng = request.args.get("lng", type=float)

    if not query:
        return jsonify([])

    db = get_db()
    # Fully Case-Insensitive Search across both Medicine Name and Salt Composition
    sql = """
    SELECT 
        s.id as shop_id, s.name as shop_name, s.city, s.lat, s.lng,
        i.id as med_id, i.med_name, i.salt_composition, i.price, i.stock_quantity, i.dosage
    FROM inventory i
    JOIN shops s ON s.id = i.shop_id
    WHERE (LOWER(i.med_name) LIKE LOWER(?) OR LOWER(i.salt_composition) LIKE LOWER(?)) 
      AND s.status = 'Verified'
    """
    search_term = f"%{query}%"
    params = [search_term, search_term]

    if city:
        sql += " AND LOWER(s.city) LIKE LOWER(?)"
        params.append(f"%{city}%")

    rows = db.execute(sql, params).fetchall()
    results = []

    for r in rows:
        item = dict(r)
        item["distance_km"] = calculate_haversine(user_lat, user_lng, r["lat"], r["lng"])
        results.append(item)

    if user_lat and user_lng:
        results.sort(key=lambda x: x["distance_km"] if x["distance_km"] is not None else float("inf"))

    return jsonify(results)

@app.route("/api/reserve", methods=["POST"])
def reserve_medicine():
    data = request.json or {}
    med_id = data.get("med_id")
    phone = data.get("phone", "").strip()

    if not med_id or not phone:
        return jsonify({"success": False, "error": "Phone number is required"}), 400

    db = get_db()
    db.execute("INSERT INTO reservations (inventory_id, customer_phone) VALUES (?, ?)", (med_id, phone))
    db.commit()
    return jsonify({"success": True, "message": "Stock successfully placed on 2-hour hold!"})

# --- AUTHENTICATION & SHOPKEEPER DASHBOARD --- #

@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        password = request.form.get("password", "").strip()
        license_number = request.form.get("license_number", "").strip()

        license_file = save_file(request.files.get("license_image"))
        gst_file = save_file(request.files.get("gst_certificate"))
        photo_file = save_file(request.files.get("shop_photo"))

        if name and password and license_number and license_file and photo_file:
            hashed_pw = generate_password_hash(password)
            db = get_db()
            try:
                cur = db.cursor()
                cur.execute("""
                    INSERT INTO shops (name, password, license_number, license_image, gst_certificate, shop_photo, status)
                    VALUES (?, ?, ?, ?, ?, ?, 'Pending')
                """, (name, hashed_pw, license_number, license_file, gst_file, photo_file))
                db.commit()
                session["shop_id"] = cur.lastrowid
                return redirect("/dashboard")
            except sqlite3.IntegrityError:
                return render_template("register.html", error="Shop name already registered.")
        return render_template("register.html", error="Please fill in all required fields.")

    return render_template("register.html")

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "").strip()

        db = get_db()
        shop = db.execute("SELECT * FROM shops WHERE name=?", (username,)).fetchone()

        if shop:
            pw_matches = check_password_hash(shop["password"], password) or shop["password"] == password
            if pw_matches:
                session["shop_id"] = shop["id"]
                return redirect("/dashboard")

        return render_template("login.html", error="Invalid Shop Name or Password.")

    return render_template("login.html")

@app.route("/logout")
def logout():
    session.clear()
    return redirect("/")

@app.route("/dashboard", methods=["GET", "POST"])
def dashboard():
    if "shop_id" not in session:
        return redirect("/login")

    db = get_db()

    if request.method == "POST":
        med_name = request.form.get("med_name", "").strip()
        salt_composition = request.form.get("salt_composition", "").strip()
        price = request.form.get("price", type=float, default=0.0)
        stock_quantity = request.form.get("stock_quantity", type=int, default=1)
        dosage = request.form.get("dosage", "").strip()

        if med_name:
            db.execute("""
                INSERT INTO inventory (shop_id, med_name, salt_composition, price, stock_quantity, dosage)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (session["shop_id"], med_name, salt_composition, price, stock_quantity, dosage))
            db.commit()

    items = db.execute("SELECT * FROM inventory WHERE shop_id=?", (session["shop_id"],)).fetchall()
    shop = db.execute("SELECT * FROM shops WHERE id=?", (session["shop_id"],)).fetchone()
    reservations = db.execute("""
        SELECT r.id, r.customer_phone, r.created_at, i.med_name 
        FROM reservations r 
        JOIN inventory i ON r.inventory_id = i.id 
        WHERE i.shop_id = ? ORDER BY r.id DESC
    """, (session["shop_id"],)).fetchall()

    return render_template("dashboard.html", items=items, shop=shop, reservations=reservations)

@app.route("/update_location", methods=["POST"])
def update_location():
    if "shop_id" not in session:
        return redirect("/login")

    lat = request.form.get("lat")
    lng = request.form.get("lng")
    city = request.form.get("city", "").strip()

    if lat and lng and city:
        db = get_db()
        db.execute("UPDATE shops SET lat = ?, lng = ?, city = ? WHERE id = ?", (lat, lng, city, session["shop_id"]))
        db.commit()

    return redirect("/dashboard")

@app.route("/delete_medicine/<int:med_id>", methods=["POST"])
def delete_medicine(med_id):
    if "shop_id" not in session:
        return redirect("/login")

    db = get_db()
    db.execute("DELETE FROM inventory WHERE id=? AND shop_id=?", (med_id, session["shop_id"]))
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
    pending = db.execute("SELECT * FROM shops WHERE status='Pending' ORDER BY id DESC").fetchall()
    verified = db.execute("SELECT * FROM shops WHERE status='Verified' ORDER BY id DESC").fetchall()
    rejected = db.execute("SELECT * FROM shops WHERE status='Rejected' ORDER BY id DESC").fetchall()

    return render_template("admin_dashboard.html", pending=pending, verified=verified, rejected=rejected)

@app.route("/approve/<int:shop_id>")
def approve(shop_id):
    if not session.get("admin"):
        return redirect("/admin")
    db = get_db()
    db.execute("UPDATE shops SET status='Verified' WHERE id=?", (shop_id,))
    db.commit()
    return redirect("/admin/dashboard")

@app.route("/reject/<int:shop_id>")
def reject(shop_id):
    if not session.get("admin"):
        return redirect("/admin")
    db = get_db()
    db.execute("UPDATE shops SET status='Rejected' WHERE id=?", (shop_id,))
    db.commit()
    return redirect("/admin/dashboard")

@app.route("/admin/logout")
def admin_logout():
    session.pop("admin", None)
    return redirect("/admin")

if __name__ == "__main__":
    app.run(debug=True, port=5000)