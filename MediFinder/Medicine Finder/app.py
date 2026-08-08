from flask import Flask, render_template, request, redirect, session, send_from_directory
import sqlite3
import os
from werkzeug.utils import secure_filename


app = Flask(__name__)
app.secret_key = "super_secret_key_for_medfinder"

# Folder to store uploaded verification files (using app.root_path ensures exact absolute pathing)
UPLOAD_FOLDER = os.path.join(app.root_path, "static", "uploads")
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER

app.config["MAX_CONTENT_LENGTH"] = 16 * 1024 * 1024

os.makedirs(UPLOAD_FOLDER, exist_ok=True)

@app.route("/uploads/<path:filename>")
def serve_upload(filename):
    return send_from_directory(app.config["UPLOAD_FOLDER"], filename)
# ---------------- DATABASE ---------------- #

def get_db():
    conn = sqlite3.connect("database.db")
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with get_db() as conn:
        conn.execute("""
        CREATE TABLE IF NOT EXISTS shops(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE,
            city TEXT,
            password TEXT,
            lat REAL,
            lng REAL,
            status TEXT DEFAULT 'Pending',
            license_number TEXT,
            license_image TEXT,
            gst_certificate TEXT,
            shop_photo TEXT
        )
        """)

        conn.execute("""
        CREATE TABLE IF NOT EXISTS inventory(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            shop_id INTEGER,
            med_name TEXT
        )
        """)

        conn.commit()

        # Database schema migrations for existing databases
        cols = [c[1] for c in conn.execute("PRAGMA table_info(shops)")]

        if "status" not in cols:
            conn.execute("ALTER TABLE shops ADD COLUMN status TEXT DEFAULT 'Pending'")
        if "license_number" not in cols:
            conn.execute("ALTER TABLE shops ADD COLUMN license_number TEXT")
        if "license_image" not in cols:
            conn.execute("ALTER TABLE shops ADD COLUMN license_image TEXT")
        if "gst_certificate" not in cols:
            conn.execute("ALTER TABLE shops ADD COLUMN gst_certificate TEXT")
        if "shop_photo" not in cols:
            conn.execute("ALTER TABLE shops ADD COLUMN shop_photo TEXT")

        conn.commit()


init_db()


def save_file(file_obj):
    """Helper function to safely save uploaded files."""
    if file_obj and file_obj.filename != "":
        filename = secure_filename(file_obj.filename)
        filepath = os.path.join(app.config["UPLOAD_FOLDER"], filename)
        file_obj.save(filepath)
        return filename
    return None


# ---------------- CUSTOMER HOME ---------------- #

@app.route("/")
def index():
    query = request.args.get("query", "").strip()
    city = request.args.get("city", "").strip()
    results = []

    if query and city:
        db = get_db()
        sql = """
        SELECT
            shops.name,
            shops.city,
            shops.lat,
            shops.lng,
            inventory.med_name
        FROM inventory
        JOIN shops
            ON shops.id = inventory.shop_id
        WHERE inventory.med_name LIKE ?
          AND shops.city LIKE ?
          AND shops.status = 'Verified'
        """
        results = db.execute(
            sql,
            ("%" + query + "%", "%" + city + "%")
        ).fetchall()

    return render_template(
        "index.html",
        results=results,
        query=query,
        city=city
    )


# ---------------- REGISTER ---------------- #

@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        password = request.form.get("password", "").strip()
        license_number = request.form.get("license_number", "").strip()

        # Save uploaded files
        license_file = save_file(request.files.get("license_image"))
        gst_file = save_file(request.files.get("gst_certificate"))  # Optional
        photo_file = save_file(request.files.get("shop_photo"))

        if name and password and license_number and license_file and photo_file:
            db = get_db()
            try:
                cur = db.cursor()
                cur.execute("""
                    INSERT INTO shops
                    (
                        name,
                        password,
                        license_number,
                        license_image,
                        gst_certificate,
                        shop_photo,
                        status
                    )
                    VALUES (?, ?, ?, ?, ?, ?, 'Pending')
                """, (
                    name,
                    password,
                    license_number,
                    license_file,
                    gst_file,
                    photo_file
                ))

                db.commit()
                session["shop_id"] = cur.lastrowid
                return redirect("/dashboard")

            except sqlite3.IntegrityError:
                return render_template(
                    "register.html",
                    error="Shop name already exists."
                )

        return render_template(
            "register.html",
            error="Please fill in all required fields and upload required documents."
        )

    return render_template("register.html")


# ---------------- LOGIN ---------------- #

@app.route("/login", methods=["GET", "POST"])
def login():
    error = None

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "").strip()

        db = get_db()
        shop = db.execute(
            """
            SELECT *
            FROM shops
            WHERE name=? AND password=?
            """,
            (username, password)
        ).fetchone()

        if shop:
            session["shop_id"] = shop["id"]
            return redirect("/dashboard")
        else:
            error = "Invalid Shop Name or Password."

    return render_template("login.html", error=error)


# ---------------- LOGOUT ---------------- #

@app.route("/logout")
def logout():
    session.clear()
    return redirect("/")


# ---------------- DASHBOARD ---------------- #

@app.route("/dashboard", methods=["GET", "POST"])
def dashboard():
    if "shop_id" not in session:
        return redirect("/login")

    db = get_db()

    if request.method == "POST":
        med_name = request.form.get("med_name", "").strip()

        if med_name:
            db.execute(
                """
                INSERT INTO inventory
                (shop_id, med_name)
                VALUES (?, ?)
                """,
                (session["shop_id"], med_name)
            )
            db.commit()

    items = db.execute(
        """
        SELECT *
        FROM inventory
        WHERE shop_id=?
        """,
        (session["shop_id"],)
    ).fetchall()

    shop = db.execute(
        """
        SELECT *
        FROM shops
        WHERE id=?
        """,
        (session["shop_id"],)
    ).fetchone()

    return render_template("dashboard.html", items=items, shop=shop)


# ---------------- UPDATE LOCATION ---------------- #

@app.route("/update_location", methods=["POST"])
def update_location():
    if "shop_id" not in session:
        return redirect("/login")

    lat = request.form.get("lat")
    lng = request.form.get("lng")
    city = request.form.get("city", "").strip()

    if lat and lng and city:
        db = get_db()
        db.execute(
            """
            UPDATE shops
            SET lat = ?, lng = ?, city = ?
            WHERE id = ?
            """,
            (lat, lng, city, session["shop_id"])
        )
        db.commit()

    return redirect("/dashboard")


# ---------------- DELETE MEDICINE ---------------- #

@app.route("/delete_medicine/<int:med_id>", methods=["POST"])
def delete_medicine(med_id):
    if "shop_id" not in session:
        return redirect("/login")

    db = get_db()
    db.execute(
        """
        DELETE FROM inventory
        WHERE id=? AND shop_id=?
        """,
        (med_id, session["shop_id"])
    )
    db.commit()

    return redirect("/dashboard")


# ===========================================================
#                    ADMIN SECTION
# ===========================================================

ADMIN_USERNAME = "admin"
ADMIN_PASSWORD = "admin123"


@app.route("/admin", methods=["GET", "POST"])
def admin():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "").strip()

        if username == ADMIN_USERNAME and password == ADMIN_PASSWORD:
            session["admin"] = True
            return redirect("/admin/dashboard")

        return render_template(
            "admin.html",
            error="Invalid admin credentials."
        )

    return render_template("admin.html")


@app.route("/admin/dashboard")
def admin_dashboard():
    if not session.get("admin"):
        return redirect("/admin")

    db = get_db()

    pending = db.execute("""
        SELECT *
        FROM shops
        WHERE status='Pending'
        ORDER BY id DESC
    """).fetchall()

    verified = db.execute("""
        SELECT *
        FROM shops
        WHERE status='Verified'
        ORDER BY id DESC
    """).fetchall()

    rejected = db.execute("""
        SELECT *
        FROM shops
        WHERE status='Rejected'
        ORDER BY id DESC
    """).fetchall()

    return render_template(
        "admin_dashboard.html",
        pending=pending,
        verified=verified,
        rejected=rejected
    )


@app.route("/approve/<int:shop_id>")
def approve(shop_id):
    if not session.get("admin"):
        return redirect("/admin")

    db = get_db()
    db.execute(
        """
        UPDATE shops
        SET status='Verified'
        WHERE id=?
        """,
        (shop_id,)
    )
    db.commit()

    return redirect("/admin/dashboard")


@app.route("/reject/<int:shop_id>")
def reject(shop_id):
    if not session.get("admin"):
        return redirect("/admin")

    db = get_db()
    db.execute(
        """
        UPDATE shops
        SET status='Rejected'
        WHERE id=?
        """,
        (shop_id,)
    )
    db.commit()

    return redirect("/admin/dashboard")


@app.route("/admin/logout")
def admin_logout():
    session.pop("admin", None)
    return redirect("/admin")


# ---------------- APP RUNNER ---------------- #

if __name__ == "__main__":
    app.run(debug=True)