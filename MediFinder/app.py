"""
MediFinder — Main Flask application.

A complete medicine-availability platform with:
  • Public search by medicine / salt, with distance sorting and live map
  • Customer accounts, reservations, favourites, reviews
  • Shopkeeper portal: inventory CRUD, location, hours, reservation workflow
  • Admin verification dashboard with stats and audit log
"""
import json
import math
import os
import re
from datetime import datetime, timedelta
from functools import wraps
from hmac import compare_digest
from urllib.parse import urlencode, urlparse
from urllib.request import Request, urlopen

from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

from flask import (
    Flask, render_template, request, redirect, session, jsonify,
    url_for, flash, abort, send_from_directory,
)
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename

from database import init_db, close_db, get_db, seed_categories
from seed import seed_demo_data

# ---------------------------------------------------------------------------
# App configuration
# ---------------------------------------------------------------------------
BASE_DIR = os.path.abspath(os.path.dirname(__file__))

app = Flask(__name__)
# Accept both /admin and /admin/ style URLs to avoid route/link edge cases.
app.url_map.strict_slashes = False
app.config.update(
    SECRET_KEY=os.environ.get("SECRET_KEY", "medfinder-local-dev-key-change-me"),
    DATABASE=os.environ.get(
        "DATABASE_PATH",
        os.path.join(BASE_DIR, "medifinder.db"),
    ),
    UPLOAD_FOLDER=os.environ.get(
        "UPLOAD_FOLDER",
        os.path.join(BASE_DIR, "static", "uploads"),
    ),
    MAX_CONTENT_LENGTH=8 * 1024 * 1024,  # 8 MB
    SESSION_COOKIE_NAME="mf_session_v2",
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
)
# Secure cookies when served behind HTTPS (production). The Arena live preview
# is also HTTPS and often embedded in an iframe, so session cookies need
# SameSite=None/Secure there; this is adjusted per request below.
IS_PRODUCTION = os.environ.get("FLASK_ENV") == "production" or bool(os.environ.get("RENDER"))
if IS_PRODUCTION:
    app.config.update(SESSION_COOKIE_SECURE=True, PREFERRED_URL_SCHEME="https")
os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)
os.makedirs(os.path.dirname(app.config["DATABASE"]) or ".", exist_ok=True)

ALLOWED_IMG = {"png", "jpg", "jpeg", "gif", "webp"}
ALLOWED_DOC = ALLOWED_IMG | {"pdf"}

ADMIN_USERNAME = os.environ.get("ADMIN_USER", "admin")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASS", "admin123")
ADMIN_TOKEN_MAX_AGE = int(os.environ.get("ADMIN_TOKEN_MAX_AGE", "28800"))  # 8 hours
ACTIVE_ADMIN_TOKENS = set()

# Default map centre (Patna, Bihar) — used before geolocation.
DEFAULT_CENTER = (25.6110, 85.1430)

# Small offline fallback so manual city searches still move the map if the
# public geocoding API is temporarily unreachable in local/dev environments.
KNOWN_CITY_CENTERS = {
    "patna": (25.6110, 85.1430, "Patna"),
    "boring road": (25.6148, 85.1125, "Patna"),
    "delhi": (28.6139, 77.2090, "Delhi"),
    "new delhi": (28.6139, 77.2090, "New Delhi"),
    "mumbai": (19.0760, 72.8777, "Mumbai"),
    "kolkata": (22.5726, 88.3639, "Kolkata"),
    "bengaluru": (12.9716, 77.5946, "Bengaluru"),
    "bangalore": (12.9716, 77.5946, "Bengaluru"),
    "hyderabad": (17.3850, 78.4867, "Hyderabad"),
    "chennai": (13.0827, 80.2707, "Chennai"),
    "pune": (18.5204, 73.8567, "Pune"),
    "lucknow": (26.8467, 80.9462, "Lucknow"),
    "jaipur": (26.9124, 75.7873, "Jaipur"),
    "ahmedabad": (23.0225, 72.5714, "Ahmedabad"),
}

# Reservation hold window
HOLD_HOURS = 2

app.teardown_appcontext(close_db)


def is_preview_request():
    """Return True for Arena/E2B HTTPS preview requests reaching Flask via proxy."""
    host = (request.headers.get("X-Forwarded-Host") or request.host or "").lower()
    proto = (request.headers.get("X-Forwarded-Proto") or request.scheme or "").split(",")[0].lower()
    remote_addr = (request.headers.get("X-Forwarded-For") or request.remote_addr or "").split(",")[0].strip()
    loopback_remote = remote_addr in {"127.0.0.1", "::1", "localhost", ""}
    preview_host = host.endswith(".e2b.app") or ".e2b.app" in host or host.endswith(".arena.ai")
    arena_proxy_request = os.environ.get("E2B_SANDBOX") == "true" and not loopback_remote
    return preview_host or proto == "https" or arena_proxy_request


@app.before_request
def configure_session_cookie_for_host():
    """Keep logins working both on localhost and inside Arena's HTTPS preview.

    Browsers treat the Arena preview as a third-party iframe in some contexts.
    Flask's default SameSite=Lax cookie is then not sent after login, which
    looks like the admin login failed. Use iframe-safe cookies only for the
    HTTPS preview host; keep localhost/dev cookies simple for normal local use.
    """
    https_preview = is_preview_request()
    app.config["SESSION_COOKIE_SAMESITE"] = "None" if https_preview else "Lax"
    app.config["SESSION_COOKIE_SECURE"] = bool(https_preview or IS_PRODUCTION)
    # Flask 3 supports CHIPS/Partitioned cookies. It helps embedded previews in
    # browsers that aggressively block ordinary third-party cookies.
    if "SESSION_COOKIE_PARTITIONED" in app.config:
        app.config["SESSION_COOKIE_PARTITIONED"] = bool(https_preview)


@app.after_request
def expire_legacy_cookie_name(response):
    """Drop stale cookies from the previous default Flask cookie name.

    The app now uses mf_session_v2 so old preview cookies cannot shadow a fresh
    login during redirects.
    """
    if app.config.get("SESSION_COOKIE_NAME") != "session" and "session=" in (request.headers.get("Cookie") or ""):
        response.delete_cookie("session", path="/")
    return response


def admin_token_serializer():
    return URLSafeTimedSerializer(app.config["SECRET_KEY"], salt="medifinder-admin-preview-auth")


def issue_admin_token(username):
    """Create a short-lived admin fallback token for cookie-hostile previews."""
    token = admin_token_serializer().dumps({"role": "admin", "u": username.lower().strip()})
    ACTIVE_ADMIN_TOKENS.add(token)
    return token


def validate_admin_token(token):
    """Validate the admin fallback token used only when browser cookies fail."""
    if not token or token not in ACTIVE_ADMIN_TOKENS:
        return False
    try:
        data = admin_token_serializer().loads(token, max_age=ADMIN_TOKEN_MAX_AGE)
    except (BadSignature, SignatureExpired):
        ACTIVE_ADMIN_TOKENS.discard(token)
        return False
    return data.get("role") == "admin" and compare_digest((data.get("u") or "").lower(), ADMIN_USERNAME.lower())


def admin_token_from_request():
    return (request.args.get("admin_token") or request.form.get("admin_token") or "").strip()


def active_admin_token():
    token = admin_token_from_request()
    return token if validate_admin_token(token) else ""


def admin_dashboard_redirect(token=""):
    token = token if validate_admin_token(token) else active_admin_token()
    if token:
        return redirect(url_for("admin_dashboard", admin_token=token))
    return redirect(url_for("admin_dashboard"))


def safe_redirect_target(target, default_endpoint):
    """Redirect only to local app paths, never arbitrary external URLs."""
    target = (target or "").strip()
    parsed = urlparse(target)
    if target.startswith("/") and not target.startswith("//") and not parsed.netloc:
        return redirect(target)
    return redirect(url_for(default_endpoint))


def parse_int(value, default=0, minimum=None, maximum=None):
    try:
        number = int(value)
    except (TypeError, ValueError):
        number = default
    if minimum is not None:
        number = max(minimum, number)
    if maximum is not None:
        number = min(maximum, number)
    return number


def parse_float(value, default=0.0, minimum=None, maximum=None):
    try:
        number = float(value)
    except (TypeError, ValueError):
        number = default
    if minimum is not None:
        number = max(minimum, number)
    if maximum is not None:
        number = min(maximum, number)
    return number


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def haversine(lat1, lng1, lat2, lng2):
    """Great-circle distance in kilometres, or None if any coord missing."""
    if None in (lat1, lng1, lat2, lng2):
        return None
    R = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlng = math.radians(lng2 - lng1)
    a = (math.sin(dlat / 2) ** 2
         + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2))
         * math.sin(dlng / 2) ** 2)
    return round(R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a)), 2)


def public_api_json(url, params=None, timeout=4):
    """Fetch JSON from a public, keyless API with a clear User-Agent.

    Nominatim/OpenStreetMap asks clients to identify themselves. Network calls
    are best effort; route handlers always provide a local fallback when this
    public API is unavailable.
    """
    query = f"?{urlencode(params or {})}" if params else ""
    req = Request(
        url + query,
        headers={
            "User-Agent": "MediFinder local pharmacy finder (demo; contact: medifinder.local)",
            "Accept": "application/json",
        },
    )
    with urlopen(req, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def city_location_fallback(db, city=""):
    """Return an approximate local centre from verified shops or Patna default."""
    if city:
        term = f"%{city.lower()}%"
        row = db.execute(
            "SELECT AVG(lat) AS lat, AVG(lng) AS lng, COALESCE(MAX(city), ?) AS city "
            "FROM shops WHERE status='Verified' AND lat IS NOT NULL AND lng IS NOT NULL "
            "AND (LOWER(city) LIKE ? OR LOWER(address) LIKE ? OR LOWER(name) LIKE ?)",
            (city, term, term, term),
        ).fetchone()
        if row and row["lat"] is not None and row["lng"] is not None:
            return {
                "lat": row["lat"], "lng": row["lng"],
                "city": row["city"] or city, "source": "local-pharmacy-average",
                "approximate": True,
            }
    normalized = city.lower().strip()
    for key, (lat, lng, label) in KNOWN_CITY_CENTERS.items():
        if normalized and (key in normalized or normalized in key):
            return {
                "lat": lat, "lng": lng, "city": label,
                "source": "known-city-centre", "approximate": True,
            }
    return {
        "lat": DEFAULT_CENTER[0], "lng": DEFAULT_CENTER[1],
        "city": city or "Patna", "source": "default-city-centre",
        "approximate": True,
    }


def allowed_file(filename, allowed=ALLOWED_IMG):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in allowed


def save_upload(file_storage, allowed=ALLOWED_IMG):
    if not file_storage or not file_storage.filename:
        return None
    if not allowed_file(file_storage.filename, allowed):
        return None
    name = secure_filename(file_storage.filename)
    # Avoid overwriting: prefix with a timestamp.
    unique = f"{datetime.utcnow().strftime('%Y%m%d%H%M%S%f')}_{name}"
    path = os.path.join(app.config["UPLOAD_FOLDER"], unique)
    file_storage.save(path)
    return unique


def log_activity(actor_type, actor_id, action, detail=""):
    try:
        db = get_db()
        db.execute(
            "INSERT INTO activity_log (actor_type, actor_id, action, detail) VALUES (?, ?, ?, ?)",
            (actor_type, actor_id, action, detail[:500] if detail else ""),
        )
        db.commit()
    except Exception:
        pass


def current_customer():
    cid = session.get("customer_id")
    if not cid:
        return None
    customer = get_db().execute("SELECT * FROM customers WHERE id=?", (cid,)).fetchone()
    if not customer:
        session.pop("customer_id", None)
    return customer


def current_shop():
    sid = session.get("shop_id")
    if not sid:
        return None
    shop = get_db().execute("SELECT * FROM shops WHERE id=?", (sid,)).fetchone()
    if not shop:
        session.pop("shop_id", None)
    return shop


def login_customer_required(fn):
    @wraps(fn)
    def wrapper(*a, **kw):
        customer = current_customer()
        if not customer:
            session.pop("customer_id", None)
            if request.path.startswith("/api/"):
                return jsonify({"ok": False, "error": "Login required"}), 401
            flash("Please sign in to continue.", "warning")
            next_url = (request.full_path or request.path).rstrip("?")
            return redirect(url_for("customer_login", next=next_url))
        return fn(*a, **kw)
    return wrapper


def login_shop_required(fn):
    @wraps(fn)
    def wrapper(*a, **kw):
        shop = current_shop()
        if not shop:
            session.pop("shop_id", None)
            if request.path.startswith("/api/") or request.is_json:
                return jsonify({"ok": False, "error": "Pharmacy login required"}), 401
            flash("Please sign in as a pharmacy.", "warning")
            return redirect(url_for("shop_login"))
        if shop["status"] == "Suspended":
            session.pop("shop_id", None)
            if request.path.startswith("/api/") or request.is_json:
                return jsonify({"ok": False, "error": "Pharmacy account is suspended"}), 403
            flash("This pharmacy account is suspended. Contact admin support.", "danger")
            return redirect(url_for("shop_login"))
        return fn(*a, **kw)
    return wrapper


def admin_required(fn):
    @wraps(fn)
    def wrapper(*a, **kw):
        token = active_admin_token()
        if not session.get("admin") and not token:
            if request.path.startswith("/api/"):
                return jsonify({"ok": False, "error": "Admin required"}), 401
            return redirect(url_for("admin"))
        if token and not session.get("admin"):
            # Rehydrate the cookie session when the browser accepts cookies, but
            # still allow the token path when the preview blocks them entirely.
            session["admin"] = True
        return fn(*a, **kw)
    return wrapper


def is_open_now(shop):
    """Return True if shop is currently open based on hours (naive local time)."""
    if not shop:
        return False
    if shop["is_open_24h"]:
        return True
    now = datetime.now().strftime("%H:%M")
    o = shop["open_time"] or "09:00"
    c = shop["close_time"] or "21:00"
    if o <= c:
        return o <= now < c
    # Overnight schedule, for example 20:00–02:00.
    return now >= o or now < c


def shop_rating(db, shop_id):
    row = db.execute(
        "SELECT ROUND(AVG(rating),1) AS avg, COUNT(*) AS n FROM reviews WHERE shop_id=?",
        (shop_id,),
    ).fetchone()
    return {"avg": row["avg"] or 0, "count": row["n"] or 0}


def expire_holds(db):
    """Mark Pending/Confirmed reservations past their held_until as Expired."""
    now = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
    db.execute(
        "UPDATE reservations SET status='Expired', updated_at=? "
        "WHERE status IN ('Pending','Confirmed') AND held_until IS NOT NULL AND held_until < ?",
        (now, now),
    )
    db.commit()


EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


# ---------------------------------------------------------------------------
# Template context
# ---------------------------------------------------------------------------
@app.context_processor
def inject_globals():
    token = active_admin_token()
    return {
        "current_customer": current_customer(),
        "current_shop": current_shop(),
        "current_year": datetime.now().year,
        "is_admin": bool(session.get("admin")) or bool(token),
        "admin_token": token,
        "DEFAULT_LAT": DEFAULT_CENTER[0],
        "DEFAULT_LNG": DEFAULT_CENTER[1],
    }


# ---------------------------------------------------------------------------
# Static uploads
# ---------------------------------------------------------------------------
@app.route("/uploads/<path:filename>")
def serve_upload(filename):
    return send_from_directory(app.config["UPLOAD_FOLDER"], filename)


# ---------------------------------------------------------------------------
# Public pages
# ---------------------------------------------------------------------------
@app.route("/")
def index():
    db = get_db()
    shops = db.execute(
        "SELECT id, name, city, address, lat, lng, is_open_24h, open_time, close_time, "
        "delivery, description, shop_photo FROM shops WHERE status='Verified'"
    ).fetchall()
    categories = db.execute("SELECT * FROM categories ORDER BY name").fetchall()
    trending = db.execute(
        "SELECT med_name, salt_composition, COUNT(*) AS n FROM inventory i "
        "JOIN shops s ON s.id=i.shop_id WHERE s.status='Verified' AND i.is_active=1 "
        "AND i.stock_quantity>0 GROUP BY med_name ORDER BY n DESC, med_name LIMIT 10"
    ).fetchall()
    return render_template(
        "index.html",
        shops=shops,
        categories=categories,
        trending=trending,
    )


@app.route("/map")
def pharmacy_map():
    """Standalone verified-pharmacy map with auto-location sorting."""
    city = request.args.get("city", "").strip()
    db = get_db()
    sql = [
        "SELECT id, name, city, address, lat, lng, is_open_24h, open_time, close_time,",
        "delivery, description, phone, shop_photo FROM shops WHERE status='Verified'",
    ]
    params = []
    if city:
        sql.append("AND (LOWER(city) LIKE ? OR LOWER(address) LIKE ?)")
        term = f"%{city.lower()}%"
        params += [term, term]
    sql.append("ORDER BY name")
    shops = db.execute(" ".join(sql), params).fetchall()
    enriched = []
    for shop in shops:
        item = dict(shop)
        item["open_now"] = is_open_now(shop)
        item["rating"] = shop_rating(db, shop["id"])
        enriched.append(item)
    return render_template("map.html", shops=enriched, city=city)


@app.route("/search")
def search_page():
    q = request.args.get("q", "").strip()
    city = request.args.get("city", "").strip()
    cat = request.args.get("cat", "").strip()
    lat = request.args.get("lat", type=float)
    lng = request.args.get("lng", type=float)
    sort = request.args.get("sort", "distance")
    dosage = request.args.get("dosage", "").strip()
    quantity = max(1, min(99, request.args.get("quantity", type=int) or 1))
    in_stock = request.args.get("in_stock", "1") == "1"
    rx = request.args.get("rx", "")
    db = get_db()
    categories = db.execute("SELECT * FROM categories ORDER BY name").fetchall()
    return render_template(
        "search.html", query=q, city=city, category=cat, sort=sort,
        dosage=dosage, quantity=quantity,
        in_stock=in_stock, rx=rx, categories=categories, lat=lat or "", lng=lng or "",
    )


@app.route("/prescription", methods=["GET", "POST"])
def prescription_upload():
    """Patient-facing prescription upload request.

    This intentionally starts as a request/verification queue rather than a full
    cart so the product stays compliant and pharmacist-reviewed.
    """
    if request.method == "POST":
        customer = current_customer()
        name = (request.form.get("name") or (customer["name"] if customer else "") or "").strip()
        phone = (request.form.get("phone") or (customer["phone"] if customer else "") or "").strip()
        city = (request.form.get("city") or (customer["city"] if customer else "") or "").strip()
        note = (request.form.get("note") or "").strip()
        lat = request.form.get("lat", type=float)
        lng = request.form.get("lng", type=float)
        upload = save_upload(request.files.get("prescription_file"), ALLOWED_DOC)

        if not phone or len(phone) < 7:
            flash("Enter a valid phone number so a pharmacy can confirm details.", "danger")
        elif not upload:
            flash("Upload a clear prescription image or PDF under 8 MB.", "danger")
        else:
            db = get_db()
            cur = db.execute(
                """INSERT INTO prescription_requests
                (customer_id, customer_name, customer_phone, city, lat, lng,
                 prescription_file, note, status)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'Submitted')""",
                (session.get("customer_id"), name or None, phone, city, lat, lng, upload, note),
            )
            db.commit()
            log_activity("customer", session.get("customer_id"), "upload_prescription", f"request#{cur.lastrowid}")
            flash("Prescription submitted. A verified pharmacy can review it and help match availability.", "success")
            return redirect(url_for("account") if session.get("customer_id") else url_for("search_page", city=city))

    return render_template("prescription.html")


@app.route("/pharmacy/<int:shop_id>")
def shop_profile(shop_id):
    db = get_db()
    shop = db.execute("SELECT * FROM shops WHERE id=?", (shop_id,)).fetchone()
    if not shop or shop["status"] != "Verified":
        abort(404)
    categories = db.execute("SELECT * FROM categories ORDER BY name").fetchall()
    cat_map = {c["id"]: c for c in categories}
    inventory = db.execute(
        "SELECT i.*, c.name AS category_name FROM inventory i "
        "LEFT JOIN categories c ON c.id=i.category_id "
        "WHERE i.shop_id=? AND i.is_active=1 ORDER BY i.med_name",
        (shop_id,),
    ).fetchall()
    reviews = db.execute(
        "SELECT * FROM reviews WHERE shop_id=? ORDER BY id DESC LIMIT 20", (shop_id,)
    ).fetchall()
    rating = shop_rating(db, shop_id)
    return render_template(
        "shop_profile.html", shop=shop, inventory=inventory,
        reviews=reviews, rating=rating, cat_map=cat_map,
        is_open=is_open_now(shop),
    )


# ---------------------------------------------------------------------------
# Public APIs
# ---------------------------------------------------------------------------
@app.route("/api/search")
def api_search():
    q = request.args.get("q", "").strip()
    city = request.args.get("city", "").strip()
    cat = request.args.get("cat", type=int)
    lat = request.args.get("lat", type=float)
    lng = request.args.get("lng", type=float)
    sort = request.args.get("sort", "distance")
    dosage = request.args.get("dosage", "").strip()
    quantity = max(1, min(99, request.args.get("quantity", type=int) or 1))
    in_stock = request.args.get("in_stock", "1") == "1"
    rx = request.args.get("rx", "")

    sql = [
        "SELECT i.id AS med_id, i.med_name, i.salt_composition, i.manufacturer,",
        "i.dosage, i.price, i.mrp, i.stock_quantity, i.prescription, i.expiry_date,",
        "i.category_id, c.name AS category_name,",
        "s.id AS shop_id, s.name AS shop_name, s.city, s.address, s.phone AS shop_phone,",
        "s.lat, s.lng, s.is_open_24h, s.open_time, s.close_time, s.delivery,",
        "s.shop_photo, s.description",
        "FROM inventory i JOIN shops s ON s.id=i.shop_id",
        "LEFT JOIN categories c ON c.id=i.category_id",
        "WHERE s.status='Verified' AND i.is_active=1",
    ]
    params = []

    if q:
        sql.append("AND (LOWER(i.med_name) LIKE ? OR LOWER(i.salt_composition) LIKE ? "
                   "OR LOWER(i.manufacturer) LIKE ?)")
        term = f"%{q.lower()}%"
        params += [term, term, term]
    if city:
        sql.append("AND (LOWER(s.city) LIKE ? OR LOWER(s.address) LIKE ?)")
        ct = f"%{city.lower()}%"
        params += [ct, ct]
    if dosage:
        sql.append("AND LOWER(i.dosage) LIKE ?")
        params.append(f"%{dosage.lower()}%")
    if cat:
        sql.append("AND i.category_id=?")
        params.append(cat)
    if in_stock:
        sql.append("AND i.stock_quantity >= ?")
        params.append(quantity)
    if rx == "1":
        sql.append("AND i.prescription=1")
    elif rx == "0":
        sql.append("AND i.prescription=0")

    rows = get_db().execute(" ".join(sql), params).fetchall()

    # Group by shop for shop-level distance; decorate results.
    results = []
    for r in rows:
        item = dict(r)
        item["distance_km"] = haversine(lat, lng, r["lat"], r["lng"])
        item["open_now"] = is_open_now(r)
        item["discount_pct"] = (
            round((1 - r["price"] / r["mrp"]) * 100)
            if r["mrp"] and r["mrp"] > r["price"] > 0 else 0
        )
        results.append(item)

    if sort == "price_asc":
        results.sort(key=lambda x: x["price"] if x["price"] is not None else 1e9)
    elif sort == "price_desc":
        results.sort(key=lambda x: x["price"] or 0, reverse=True)
    elif sort == "stock":
        results.sort(key=lambda x: x["stock_quantity"] or 0, reverse=True)
    else:  # distance
        results.sort(key=lambda x: x["distance_km"] if x["distance_km"] is not None else 1e9)

    return jsonify({"ok": True, "count": len(results), "requested_quantity": quantity, "results": results})


@app.route("/api/autocomplete")
def api_autocomplete():
    q = request.args.get("q", "").strip().lower()
    if not q or len(q) < 2:
        return jsonify([])
    rows = get_db().execute(
        "SELECT DISTINCT med_name, salt_composition FROM inventory i "
        "JOIN shops s ON s.id=i.shop_id "
        "WHERE s.status='Verified' AND i.is_active=1 "
        "AND (LOWER(i.med_name) LIKE ? OR LOWER(i.salt_composition) LIKE ?) "
        "ORDER BY i.med_name LIMIT 10",
        (f"%{q}%", f"%{q}%"),
    ).fetchall()
    return jsonify([dict(r) for r in rows])


@app.route("/api/geocode")
def api_geocode():
    """Geocode a city/address using the public OpenStreetMap Nominatim API.

    The API is listed in public-apis and requires no key. If it is unreachable,
    MediFinder falls back to verified-pharmacy coordinates from the local DB.
    """
    q = request.args.get("q", "").strip()
    if len(q) < 2:
        return jsonify({"ok": False, "error": "Enter at least two characters."}), 400

    results = []
    try:
        data = public_api_json("https://nominatim.openstreetmap.org/search", {
            "format": "jsonv2", "q": q, "limit": 5, "countrycodes": "in",
            "addressdetails": 1,
        })
        for place in data[:5]:
            addr = place.get("address") or {}
            results.append({
                "name": place.get("display_name", q),
                "lat": float(place["lat"]), "lng": float(place["lon"]),
                "city": addr.get("city") or addr.get("town") or addr.get("village")
                        or addr.get("suburb") or addr.get("state_district") or q,
                "source": "openstreetmap-nominatim",
                "approximate": False,
            })
    except Exception:
        results = []

    if not results:
        fallback = city_location_fallback(get_db(), q)
        results.append({"name": fallback["city"], **fallback})

    return jsonify({"ok": True, "results": results})


@app.route("/api/reverse-geocode")
def api_reverse_geocode():
    """Reverse geocode coordinates using Nominatim with a local fallback."""
    lat = request.args.get("lat", type=float)
    lng = request.args.get("lng", type=float)
    if lat is None or lng is None:
        return jsonify({"ok": False, "error": "Coordinates required."}), 400

    try:
        data = public_api_json("https://nominatim.openstreetmap.org/reverse", {
            "format": "jsonv2", "lat": lat, "lon": lng, "zoom": 12, "addressdetails": 1,
        })
        addr = data.get("address") or {}
        city = addr.get("city") or addr.get("town") or addr.get("village") \
            or addr.get("suburb") or addr.get("county") or addr.get("state_district") or ""
        if city:
            return jsonify({
                "ok": True, "city": city,
                "display_name": data.get("display_name", city),
                "source": "openstreetmap-nominatim",
                "approximate": False,
            })
    except Exception:
        pass

    db = get_db()
    rows = db.execute(
        "SELECT city, lat, lng FROM shops WHERE status='Verified' AND lat IS NOT NULL AND lng IS NOT NULL"
    ).fetchall()
    nearest = None
    for row in rows:
        d = haversine(lat, lng, row["lat"], row["lng"])
        if d is not None and (nearest is None or d < nearest[0]):
            nearest = (d, row["city"])
    return jsonify({
        "ok": True, "city": (nearest[1] if nearest else "Patna"),
        "source": "nearest-local-pharmacy", "approximate": True,
    })


@app.route("/api/location/estimate")
def api_location_estimate():
    """Best-effort location fallback for preview/browser geolocation failures."""
    city = request.args.get("city", "").strip()
    fallback = city_location_fallback(get_db(), city)
    return jsonify({"ok": True, **fallback})


@app.route("/api/shops/nearby")
def api_nearby_shops():
    lat = request.args.get("lat", type=float)
    lng = request.args.get("lng", type=float)
    if lat is None or lng is None:
        return jsonify({"ok": False, "error": "Coordinates required"}), 400
    db = get_db()
    rows = db.execute(
        "SELECT id, name, city, address, lat, lng, is_open_24h, open_time, close_time, "
        "delivery, shop_photo, description FROM shops WHERE status='Verified'"
    ).fetchall()
    shops = []
    for r in rows:
        d = haversine(lat, lng, r["lat"], r["lng"])
        if d is not None:
            item = dict(r)
            item["distance_km"] = d
            item["open_now"] = is_open_now(r)
            item["rating"] = shop_rating(db, r["id"])
            shops.append(item)
    shops.sort(key=lambda x: x["distance_km"])
    return jsonify({"ok": True, "shops": shops[:20]})


@app.route("/api/shop/<int:shop_id>")
def api_shop(shop_id):
    db = get_db()
    shop = db.execute("SELECT * FROM shops WHERE id=? AND status='Verified'", (shop_id,)).fetchone()
    if not shop:
        return jsonify({"ok": False, "error": "Not found"}), 404
    inventory = db.execute(
        "SELECT i.*, c.name AS category_name FROM inventory i "
        "LEFT JOIN categories c ON c.id=i.category_id "
        "WHERE i.shop_id=? AND i.is_active=1 ORDER BY i.med_name", (shop_id,)
    ).fetchall()
    data = dict(shop)
    data["inventory"] = [dict(x) for x in inventory]
    data["rating"] = shop_rating(db, shop_id)
    data["open_now"] = is_open_now(shop)
    return jsonify({"ok": True, "shop": data})


@app.route("/api/reserve", methods=["POST"])
def api_reserve():
    data = request.get_json(silent=True) or request.form
    med_id = parse_int(data.get("med_id"), default=0, minimum=0)
    phone = (data.get("phone") or "").strip()
    name = (data.get("name") or "").strip()
    qty = parse_int(data.get("quantity"), default=1, minimum=1, maximum=99)
    note = (data.get("note") or "").strip()

    if not med_id or not phone:
        return jsonify({"ok": False, "error": "Medicine and phone are required."}), 400
    if len(phone) < 7:
        return jsonify({"ok": False, "error": "Enter a valid phone number."}), 400

    db = get_db()
    expire_holds(db)
    item = db.execute(
        "SELECT i.*, s.name AS shop_name FROM inventory i JOIN shops s ON s.id=i.shop_id "
        "WHERE i.id=? AND s.status='Verified' AND i.is_active=1", (med_id,)
    ).fetchone()
    if not item:
        return jsonify({"ok": False, "error": "Medicine not available."}), 404
    active_holds = db.execute(
        "SELECT COALESCE(SUM(quantity), 0) FROM reservations "
        "WHERE inventory_id=? AND status IN ('Pending', 'Confirmed')",
        (med_id,),
    ).fetchone()[0] or 0
    available_qty = max(0, (item["stock_quantity"] or 0) - active_holds)
    if available_qty < qty:
        return jsonify({"ok": False, "error": f"Only {available_qty} units are currently available to hold."}), 400

    held_until = datetime.utcnow() + timedelta(hours=HOLD_HOURS)
    cur = db.execute(
        "INSERT INTO reservations (inventory_id, shop_id, customer_id, customer_name, "
        "customer_phone, quantity, note, status, held_until) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, 'Pending', ?)",
        (med_id, item["shop_id"], session.get("customer_id"),
         name or None, phone, qty, note, held_until),
    )
    db.commit()
    log_activity("customer", session.get("customer_id"), "reserve",
                 f"{qty}x item#{med_id} at shop#{item['shop_id']}")
    return jsonify({
        "ok": True,
        "reservation_id": cur.lastrowid,
        "message": f"Reserved! Pick up at {item['shop_name']} within {HOLD_HOURS} hours.",
        "held_until": held_until.isoformat(),
    })


# ---------------------------------------------------------------------------
# Customer auth
# ---------------------------------------------------------------------------
@app.route("/account/register", methods=["GET", "POST"])
def customer_register():
    if session.get("customer_id"):
        if current_customer():
            return redirect(url_for("account"))
        session.pop("customer_id", None)
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip().lower()
        phone = request.form.get("phone", "").strip()
        password = request.form.get("password", "")
        city = request.form.get("city", "").strip()
        if not name or not email or not password:
            flash("Name, email and password are required.", "danger")
        elif not EMAIL_RE.match(email):
            flash("Enter a valid email address.", "danger")
        elif len(password) < 6:
            flash("Password must be at least 6 characters.", "danger")
        else:
            db = get_db()
            if db.execute("SELECT 1 FROM customers WHERE email=?", (email,)).fetchone():
                flash("An account with that email already exists.", "danger")
            else:
                db.execute(
                    "INSERT INTO customers (name,email,phone,password_hash,city) VALUES (?, ?, ?, ?, ?)",
                    (name, email, phone, generate_password_hash(password), city),
                )
                db.commit()
                uid = db.execute("SELECT id FROM customers WHERE email=?", (email,)).fetchone()["id"]
                session.clear()
                session["customer_id"] = uid
                log_activity("customer", uid, "register", name)
                flash("Welcome to MediFinder!", "success")
                return safe_redirect_target(request.args.get("next"), "account")
    return render_template("customer_auth.html", mode="register")


@app.route("/account/login", methods=["GET", "POST"])
def customer_login():
    if session.get("customer_id"):
        if current_customer():
            return redirect(url_for("account"))
        session.pop("customer_id", None)
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        db = get_db()
        user = db.execute("SELECT * FROM customers WHERE email=?", (email,)).fetchone()
        if user and check_password_hash(user["password_hash"], password):
            session.clear()
            session["customer_id"] = user["id"]
            log_activity("customer", user["id"], "login", "")
            flash("Signed in.", "success")
            return safe_redirect_target(request.args.get("next"), "account")
        flash("Invalid email or password.", "danger")
    return render_template("customer_auth.html", mode="login")


@app.route("/account/logout")
def customer_logout():
    session.pop("customer_id", None)
    flash("Signed out.", "info")
    return redirect(url_for("index"))


@app.route("/account")
@login_customer_required
def account():
    db = get_db()
    customer = current_customer()
    expire_holds(db)
    reservations = db.execute(
        "SELECT r.*, i.med_name, i.dosage, i.price, s.name AS shop_name, s.city AS shop_city, "
        "s.status AS shop_status, s.lat AS shop_lat, s.lng AS shop_lng "
        "FROM reservations r JOIN inventory i ON i.id=r.inventory_id "
        "JOIN shops s ON s.id=r.shop_id WHERE r.customer_id=? "
        "ORDER BY CASE r.status WHEN 'Pending' THEN 0 WHEN 'Confirmed' THEN 1 "
        "WHEN 'Collected' THEN 2 ELSE 3 END, r.id DESC",
        (customer["id"],),
    ).fetchall()
    favourites = db.execute(
        "SELECT * FROM favourites WHERE customer_id=? ORDER BY id DESC", (customer["id"],)
    ).fetchall()
    reviews = db.execute(
        "SELECT rv.*, s.name AS shop_name, s.status AS shop_status FROM reviews rv JOIN shops s ON s.id=rv.shop_id "
        "WHERE rv.customer_id=? ORDER BY rv.id DESC", (customer["id"],),
    ).fetchall()
    prescription_requests = db.execute(
        "SELECT * FROM prescription_requests WHERE customer_id=? ORDER BY id DESC",
        (customer["id"],),
    ).fetchall()
    return render_template(
        "account.html", reservations=reservations,
        favourites=favourites, reviews=reviews,
        prescription_requests=prescription_requests,
    )


@app.route("/account/reservation/<int:rid>/cancel", methods=["POST"])
@login_customer_required
def cancel_reservation(rid):
    db = get_db()
    r = db.execute("SELECT * FROM reservations WHERE id=? AND customer_id=?",
                   (rid, session["customer_id"])).fetchone()
    if not r:
        abort(404)
    if r["status"] not in {"Pending", "Confirmed"}:
        if request.path.startswith("/api/") or request.is_json:
            return jsonify({"ok": False, "error": "Only active holds can be cancelled."}), 400
        flash("Only active holds can be cancelled.", "warning")
        return redirect(url_for("account"))
    db.execute("UPDATE reservations SET status='Cancelled', updated_at=? WHERE id=?",
               (datetime.utcnow(), rid))
    db.commit()
    log_activity("customer", session["customer_id"], "cancel_reservation", f"reservation#{rid}")
    if request.path.startswith("/api/") or request.is_json:
        return jsonify({"ok": True})
    flash("Reservation cancelled.", "info")
    return redirect(url_for("account"))


@app.route("/api/favourites", methods=["GET", "POST", "DELETE"])
@login_customer_required
def favourites_api():
    db = get_db()
    cid = session["customer_id"]
    if request.method == "GET":
        rows = db.execute("SELECT * FROM favourites WHERE customer_id=? ORDER BY id DESC", (cid,)).fetchall()
        return jsonify({"ok": True, "favourites": [dict(r) for r in rows]})

    if request.method == "POST" and not request.is_json and request.form.get("id"):
        fid = parse_int(request.form.get("id"), default=0)
        db.execute("DELETE FROM favourites WHERE id=? AND customer_id=?", (fid, cid))
        db.commit()
        flash("Saved medicine removed.", "info")
        return redirect(url_for("account"))

    data = request.get_json(silent=True) or {}
    med = (data.get("med_name") or "").strip()
    salt = (data.get("salt") or "").strip()
    fid = data.get("id")
    if request.method == "DELETE":
        if fid:
            db.execute("DELETE FROM favourites WHERE id=? AND customer_id=?", (fid, cid))
        else:
            db.execute("DELETE FROM favourites WHERE customer_id=? AND med_name=? AND salt=?",
                       (cid, med, salt))
        db.commit()
        return jsonify({"ok": True})
    if not med:
        return jsonify({"ok": False, "error": "Medicine name required"}), 400
    try:
        db.execute("INSERT INTO favourites (customer_id, med_name, salt) VALUES (?, ?, ?)",
                   (cid, med, salt))
        db.commit()
    except Exception:
        return jsonify({"ok": False, "error": "Already in favourites"}), 409
    return jsonify({"ok": True})


@app.route("/api/shops/<int:shop_id>/review", methods=["POST"])
@login_customer_required
def post_review(shop_id):
    data = request.get_json(silent=True) or {}
    rating = parse_int(data.get("rating"), default=0)
    comment = (data.get("comment") or "").strip()
    if rating < 1 or rating > 5:
        return jsonify({"ok": False, "error": "Rating must be 1–5"}), 400
    db = get_db()
    shop = db.execute("SELECT 1 FROM shops WHERE id=? AND status='Verified'", (shop_id,)).fetchone()
    if not shop:
        return jsonify({"ok": False, "error": "Shop not found"}), 404
    c = current_customer()
    db.execute(
        "INSERT INTO reviews (shop_id, customer_id, customer_name, rating, comment) VALUES (?, ?, ?, ?, ?)",
        (shop_id, c["id"], c["name"], rating, comment),
    )
    db.commit()
    return jsonify({"ok": True, "rating": shop_rating(db, shop_id)})


# ---------------------------------------------------------------------------
# Shop (pharmacy) auth & dashboard
# ---------------------------------------------------------------------------
@app.route("/pharmacy/register", methods=["GET", "POST"])
def shop_register():
    if session.get("shop_id"):
        shop = current_shop()
        if shop and shop["status"] != "Suspended":
            return redirect(url_for("shop_dashboard"))
        session.pop("shop_id", None)
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip().lower()
        phone = request.form.get("phone", "").strip()
        owner = request.form.get("owner_name", "").strip()
        password = request.form.get("password", "")
        license_no = request.form.get("license_number", "").strip()
        address = request.form.get("address", "").strip()
        city = request.form.get("city", "").strip()
        state = request.form.get("state", "").strip()
        pincode = request.form.get("pincode", "").strip()
        description = request.form.get("description", "").strip()
        if not name or not password or not license_no:
            flash("Shop name, password and drug licence number are required.", "danger")
        elif len(password) < 6:
            flash("Password must be at least 6 characters.", "danger")
        else:
            license_img = save_upload(request.files.get("license_image"))
            shop_photo = save_upload(request.files.get("shop_photo"))
            gst = save_upload(request.files.get("gst_certificate"), ALLOWED_DOC)
            db = get_db()
            duplicate = db.execute(
                "SELECT 1 FROM shops WHERE LOWER(name)=? OR (?<>'' AND LOWER(email)=?)",
                (name.lower(), email, email),
            ).fetchone()
            if duplicate:
                flash("A pharmacy with that name or email is already registered.", "danger")
            else:
                cur = db.execute(
                    """INSERT INTO shops
                    (name,email,phone,owner_name,password_hash,license_number,
                     license_image,gst_certificate,shop_photo,description,
                     address,city,state,pincode,status)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'Pending')""",
                    (name, email, phone, owner, generate_password_hash(password),
                     license_no, license_img, gst, shop_photo, description,
                     address, city, state, pincode),
                )
                db.commit()
                session.clear()
                session["shop_id"] = cur.lastrowid
                log_activity("shop", cur.lastrowid, "register", name)
                flash("Registration submitted. You can set up inventory while admin verifies your documents.", "info")
                return redirect(url_for("shop_dashboard"))
    return render_template("shop_register.html")


@app.route("/pharmacy/login", methods=["GET", "POST"])
def shop_login():
    if session.get("shop_id"):
        shop = current_shop()
        if shop and shop["status"] != "Suspended":
            return redirect(url_for("shop_dashboard"))
        session.pop("shop_id", None)
    if request.method == "POST":
        name = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        db = get_db()
        shop = db.execute("SELECT * FROM shops WHERE LOWER(name)=?", (name.lower(),)).fetchone()
        if not shop and "@" in name:
            shop = db.execute("SELECT * FROM shops WHERE LOWER(email)=?", (name.lower(),)).fetchone()
        if shop and shop["password_hash"] and check_password_hash(shop["password_hash"], password):
            if shop["status"] == "Suspended":
                flash("This pharmacy account is suspended. Contact admin support.", "danger")
            else:
                session.clear()
                session["shop_id"] = shop["id"]
                log_activity("shop", shop["id"], "login", "")
                return redirect(url_for("shop_dashboard"))
        else:
            flash("Invalid credentials.", "danger")
    return render_template("shop_login.html")


@app.route("/pharmacy/logout")
def shop_logout():
    session.pop("shop_id", None)
    return redirect(url_for("index"))


@app.route("/pharmacy/dashboard")
@login_shop_required
def shop_dashboard():
    db = get_db()
    shop = current_shop()
    expire_holds(db)
    categories = db.execute("SELECT * FROM categories ORDER BY name").fetchall()
    inventory = db.execute(
        "SELECT i.*, c.name AS category_name FROM inventory i "
        "LEFT JOIN categories c ON c.id=i.category_id WHERE i.shop_id=? "
        "ORDER BY i.is_active DESC, i.med_name", (shop["id"],),
    ).fetchall()
    reservations = db.execute(
        "SELECT r.*, i.med_name, i.dosage FROM reservations r "
        "JOIN inventory i ON i.id=r.inventory_id WHERE r.shop_id=? "
        "ORDER BY CASE r.status WHEN 'Pending' THEN 0 WHEN 'Confirmed' THEN 1 ELSE 2 END, r.id DESC",
        (shop["id"],),
    ).fetchall()
    # Aggregate stats
    stats = db.execute(
        "SELECT COUNT(*) AS total_items, "
        "SUM(CASE WHEN stock_quantity>0 THEN 1 ELSE 0 END) AS in_stock, "
        "SUM(CASE WHEN stock_quantity=0 THEN 1 ELSE 0 END) AS out_stock, "
        "SUM(stock_quantity) AS total_units, "
        "SUM(CASE WHEN expiry_date IS NOT NULL AND expiry_date < date('now','+30 day') THEN 1 ELSE 0 END) AS expiring, "
        "COALESCE(SUM(price*stock_quantity),0) AS inventory_value "
        "FROM inventory WHERE shop_id=? AND is_active=1",
        (shop["id"],),
    ).fetchone()
    res_stats = dict(db.execute(
        "SELECT "
        "SUM(CASE WHEN status='Pending' THEN 1 ELSE 0 END) AS pending, "
        "SUM(CASE WHEN status='Confirmed' THEN 1 ELSE 0 END) AS confirmed, "
        "SUM(CASE WHEN status='Collected' THEN 1 ELSE 0 END) AS collected, "
        "COUNT(*) AS total FROM reservations WHERE shop_id=?",
        (shop["id"],),
    ).fetchone())
    low_stock = db.execute(
        "SELECT * FROM inventory WHERE shop_id=? AND is_active=1 AND stock_quantity BETWEEN 0 AND 9 "
        "ORDER BY stock_quantity ASC, med_name LIMIT 6",
        (shop["id"],),
    ).fetchall()
    expiring_items = db.execute(
        "SELECT * FROM inventory WHERE shop_id=? AND is_active=1 AND expiry_date IS NOT NULL "
        "AND expiry_date < date('now','+45 day') ORDER BY expiry_date ASC LIMIT 6",
        (shop["id"],),
    ).fetchall()
    return render_template(
        "shop_dashboard.html",
        shop=shop, categories=categories, inventory=inventory,
        reservations=reservations, stats=stats, res_stats=res_stats,
        low_stock=low_stock, expiring_items=expiring_items,
    )


@app.route("/pharmacy/inventory/add", methods=["POST"])
@login_shop_required
def add_inventory():
    shop = current_shop()
    f = request.form
    med = f.get("med_name", "").strip()
    if not med:
        flash("Medicine name is required.", "danger")
        return redirect(url_for("shop_dashboard"))
    price = parse_float(f.get("price"), default=0, minimum=0)
    mrp = parse_float(f.get("mrp"), default=0, minimum=0)
    stock = parse_int(f.get("stock_quantity"), default=0, minimum=0)
    db = get_db()
    db.execute(
        """INSERT INTO inventory
        (shop_id, med_name, salt_composition, category_id, manufacturer, batch_no,
         expiry_date, price, mrp, stock_quantity, dosage, prescription, is_active)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1)""",
        (shop["id"], med, f.get("salt_composition", "").strip(),
         f.get("category_id", type=int), f.get("manufacturer", "").strip(),
         f.get("batch_no", "").strip(), f.get("expiry_date") or None,
         price, mrp, stock, f.get("dosage", "").strip(),
         1 if f.get("prescription") else 0),
    )
    db.commit()
    flash(f"{med} added to inventory.", "success")
    return redirect(url_for("shop_dashboard"))


@app.route("/pharmacy/inventory/<int:item_id>/update", methods=["POST"])
@login_shop_required
def update_inventory(item_id):
    shop = current_shop()
    db = get_db()
    item = db.execute("SELECT * FROM inventory WHERE id=? AND shop_id=?",
                      (item_id, shop["id"])).fetchone()
    if not item:
        abort(404)
    if request.is_json:
        data = request.get_json(silent=True) or {}
        allowed = {"med_name", "salt_composition", "manufacturer", "batch_no",
                   "expiry_date", "dosage", "category_id", "price", "mrp",
                   "stock_quantity", "prescription", "is_active"}
        fields, values = [], []
        for k, v in data.items():
            if k not in allowed:
                continue
            if k in {"price", "mrp"}:
                v = parse_float(v, default=0, minimum=0)
            elif k == "stock_quantity":
                v = parse_int(v, default=0, minimum=0)
            elif k == "category_id":
                v = parse_int(v, default=0, minimum=0) or None
            elif k in {"prescription", "is_active"}:
                v = 1 if str(v).lower() in {"1", "true", "yes", "on"} else 0
            elif k == "med_name":
                v = str(v or "").strip()
                if not v:
                    return jsonify({"ok": False, "error": "Medicine name is required"}), 400
            elif isinstance(v, str):
                v = v.strip()
            fields.append(f"{k}=?")
            values.append(v)
        if not fields:
            return jsonify({"ok": False, "error": "Nothing to update"}), 400
        fields.append("updated_at=?")
        values.append(datetime.utcnow())
        values.append(item_id)
        db.execute(f"UPDATE inventory SET {', '.join(fields)} WHERE id=?", values)
        db.commit()
        return jsonify({"ok": True})
    # Form fallback (stock quick-update)
    stock_raw = request.form.get("stock_quantity")
    price_raw = request.form.get("price")
    if stock_raw not in (None, ""):
        stock = parse_int(stock_raw, default=item["stock_quantity"] or 0, minimum=0)
        db.execute("UPDATE inventory SET stock_quantity=?, updated_at=? WHERE id=?",
                   (stock, datetime.utcnow(), item_id))
    if price_raw not in (None, ""):
        price = parse_float(price_raw, default=item["price"] or 0, minimum=0)
        db.execute("UPDATE inventory SET price=?, updated_at=? WHERE id=?",
                   (price, datetime.utcnow(), item_id))
    db.commit()
    flash("Inventory updated.", "success")
    return redirect(url_for("shop_dashboard"))


@app.route("/pharmacy/inventory/<int:item_id>/delete", methods=["POST"])
@login_shop_required
def delete_inventory(item_id):
    shop = current_shop()
    db = get_db()
    db.execute("DELETE FROM inventory WHERE id=? AND shop_id=?", (item_id, shop["id"]))
    db.commit()
    flash("Item removed.", "info")
    return redirect(url_for("shop_dashboard"))


@app.route("/pharmacy/profile", methods=["GET", "POST"])
@login_shop_required
def shop_profile_update():
    shop = current_shop()
    if request.method == "POST":
        f = request.form
        db = get_db()
        new_name = f.get("name", "").strip()
        new_email = f.get("email", "").strip().lower()
        if not new_name:
            flash("Shop name is required.", "danger")
            return redirect(url_for("shop_dashboard"))
        duplicate = db.execute(
            "SELECT 1 FROM shops WHERE id<>? AND (LOWER(name)=? OR (?<>'' AND LOWER(email)=?))",
            (shop["id"], new_name.lower(), new_email, new_email),
        ).fetchone()
        if duplicate:
            flash("Another pharmacy already uses that name or email.", "danger")
            return redirect(url_for("shop_dashboard"))
        fields = ["name", "email", "phone", "owner_name", "description",
                  "address", "city", "state", "pincode", "open_time", "close_time"]
        values = [f.get(k, "").strip() for k in fields]
        values[0] = new_name
        values[1] = new_email
        lat = f.get("lat", type=float)
        lng = f.get("lng", type=float)
        values += [lat, lng, 1 if f.get("is_open_24h") else 0,
                   1 if f.get("delivery") else 0, shop["id"]]
        photo = save_upload(request.files.get("shop_photo"))
        if photo:
            db.execute("UPDATE shops SET shop_photo=? WHERE id=?", (photo, shop["id"]))
        db.execute(
            f"UPDATE shops SET {', '.join(k+'=?' for k in fields)}, "
            "lat=?, lng=?, is_open_24h=?, delivery=? WHERE id=?",
            values,
        )
        db.commit()
        flash("Profile updated.", "success")
        return redirect(url_for("shop_dashboard"))
    return redirect(url_for("shop_dashboard"))


@app.route("/pharmacy/reservation/<int:rid>/<action>", methods=["POST"])
@login_shop_required
def reservation_action(rid, action):
    shop = current_shop()
    if action not in {"confirm", "collect", "cancel"}:
        abort(404)
    status_map = {"confirm": "Confirmed", "collect": "Collected", "cancel": "Cancelled"}
    db = get_db()
    r = db.execute("SELECT * FROM reservations WHERE id=? AND shop_id=?",
                   (rid, shop["id"])).fetchone()
    if not r:
        abort(404)
    if r["status"] not in {"Pending", "Confirmed"}:
        message = "Only active reservations can be changed."
        if request.is_json:
            return jsonify({"ok": False, "error": message}), 400
        flash(message, "warning")
        return redirect(url_for("shop_dashboard"))

    new_status = status_map[action]
    if action == "collect":
        stock = db.execute("SELECT stock_quantity FROM inventory WHERE id=?", (r["inventory_id"],)).fetchone()
        if not stock or stock["stock_quantity"] < r["quantity"]:
            message = "Not enough stock to mark this hold as collected."
            if request.is_json:
                return jsonify({"ok": False, "error": message}), 400
            flash(message, "danger")
            return redirect(url_for("shop_dashboard"))

    db.execute("UPDATE reservations SET status=?, updated_at=? WHERE id=?",
               (new_status, datetime.utcnow(), rid))
    # When collected, decrement stock once. Non-active statuses were rejected above.
    if new_status == "Collected":
        db.execute("UPDATE inventory SET stock_quantity = MAX(0, stock_quantity - ?) WHERE id=?",
                   (r["quantity"], r["inventory_id"]))
    db.commit()
    log_activity("shop", shop["id"], f"reservation_{action}", f"reservation#{rid}")
    if request.is_json:
        return jsonify({"ok": True, "status": new_status})
    flash(f"Reservation marked {new_status}.", "success")
    return redirect(url_for("shop_dashboard"))


# ---------------------------------------------------------------------------
# Admin
# ---------------------------------------------------------------------------
@app.route("/admin/login", methods=["GET", "POST"])
@app.route("/admin", methods=["GET", "POST"])
def admin():
    token = active_admin_token()
    if session.get("admin") or token:
        return admin_dashboard_redirect(token)
    if request.method == "POST":
        u = request.form.get("username", "").strip()
        p = request.form.get("password", "").strip()
        username_ok = compare_digest(u.lower(), ADMIN_USERNAME.lower())
        password_ok = compare_digest(p, ADMIN_PASSWORD)
        if username_ok and password_ok:
            session.clear()
            session["admin"] = True
            log_activity("admin", None, "login", u)
            # Some live-preview iframes block cookies altogether. In that case,
            # carry a short-lived signed token through admin links/forms so the
            # demo console still opens after the credential check succeeds.
            fallback_token = issue_admin_token(u) if is_preview_request() else ""
            return admin_dashboard_redirect(fallback_token)
        flash("Invalid admin credentials. For the demo, use admin / admin123.", "danger")
    return render_template("admin_login.html")


@app.route("/admin/dashboard")
@admin_required
def admin_dashboard():
    db = get_db()
    pending = db.execute(
        "SELECT * FROM shops WHERE status='Pending' ORDER BY id DESC").fetchall()
    verified = db.execute(
        "SELECT * FROM shops WHERE status='Verified' ORDER BY name").fetchall()
    rejected = db.execute(
        "SELECT * FROM shops WHERE status IN ('Rejected', 'Suspended') ORDER BY status, id DESC").fetchall()
    stats = dict(db.execute(
        "SELECT "
        "(SELECT COUNT(*) FROM shops) AS shops, "
        "(SELECT COUNT(*) FROM shops WHERE status='Verified') AS verified, "
        "(SELECT COUNT(*) FROM shops WHERE status='Pending') AS pending, "
        "(SELECT COUNT(*) FROM customers) AS customers, "
        "(SELECT COUNT(*) FROM inventory) AS inventory, "
        "(SELECT COUNT(*) FROM reservations) AS reservations, "
        "(SELECT COUNT(*) FROM prescription_requests) AS prescriptions, "
        "(SELECT COUNT(*) FROM reviews) AS reviews"
    ).fetchone())
    recent_reservations = db.execute(
        "SELECT r.*, i.med_name, s.name AS shop_name FROM reservations r "
        "JOIN inventory i ON i.id=r.inventory_id JOIN shops s ON s.id=r.shop_id "
        "ORDER BY r.id DESC LIMIT 15"
    ).fetchall()
    prescription_requests = db.execute(
        "SELECT * FROM prescription_requests ORDER BY id DESC LIMIT 15"
    ).fetchall()
    logs = db.execute(
        "SELECT * FROM activity_log ORDER BY id DESC LIMIT 30").fetchall()
    return render_template(
        "admin_dashboard.html",
        pending=pending, verified=verified, rejected=rejected,
        stats=stats, recent_reservations=recent_reservations,
        prescription_requests=prescription_requests, logs=logs,
    )


@app.route("/admin/shop/<int:shop_id>/<action>", methods=["POST"])
@admin_required
def admin_shop_action(shop_id, action):
    if action not in {"approve", "reject", "suspend", "reinstate", "delete"}:
        abort(404)
    db = get_db()
    shop = db.execute("SELECT * FROM shops WHERE id=?", (shop_id,)).fetchone()
    if not shop:
        abort(404)
    note = (request.form.get("note") or "").strip()
    if action == "approve":
        db.execute("UPDATE shops SET status='Verified', rejection_note=NULL WHERE id=?", (shop_id,))
        log_activity("admin", None, "approve_shop", shop["name"])
    elif action == "reject":
        db.execute("UPDATE shops SET status='Rejected', rejection_note=? WHERE id=?", (note, shop_id))
        log_activity("admin", None, "reject_shop", f"{shop['name']}: {note}")
    elif action == "suspend":
        db.execute("UPDATE shops SET status='Suspended', rejection_note=? WHERE id=?",
                   (note or "Suspended by admin", shop_id,))
        log_activity("admin", None, "suspend_shop", shop["name"])
    elif action == "reinstate":
        db.execute("UPDATE shops SET status='Verified', rejection_note=NULL WHERE id=?", (shop_id,))
        log_activity("admin", None, "reinstate_shop", shop["name"])
    elif action == "delete":
        db.execute("DELETE FROM shops WHERE id=?", (shop_id,))
        log_activity("admin", None, "delete_shop", shop["name"])
    db.commit()
    return admin_dashboard_redirect()


@app.route("/admin/prescription/<int:request_id>/<action>", methods=["POST"])
@admin_required
def admin_prescription_action(request_id, action):
    status_map = {"review": "Reviewing", "match": "Matched", "close": "Closed"}
    if action not in status_map:
        abort(404)
    db = get_db()
    req = db.execute("SELECT * FROM prescription_requests WHERE id=?", (request_id,)).fetchone()
    if not req:
        abort(404)
    db.execute(
        "UPDATE prescription_requests SET status=?, updated_at=? WHERE id=?",
        (status_map[action], datetime.utcnow(), request_id),
    )
    db.commit()
    log_activity("admin", None, f"prescription_{action}", f"request#{request_id}")
    flash(f"Prescription request marked {status_map[action]}.", "success")
    return admin_dashboard_redirect()


@app.route("/admin/logout")
def admin_logout():
    token = admin_token_from_request()
    if token:
        ACTIVE_ADMIN_TOKENS.discard(token)
    session.pop("admin", None)
    return redirect(url_for("admin"))


# ---------------------------------------------------------------------------
# Error handlers
# ---------------------------------------------------------------------------
@app.errorhandler(404)
def not_found(e):
    return render_template("error.html", code=404,
                           message="We couldn't find what you were looking for."), 404


@app.errorhandler(500)
def server_error(e):
    return render_template("error.html", code=500,
                           message="Something went wrong on our side."), 500


# ---------------------------------------------------------------------------
# CLI / bootstrap
# ---------------------------------------------------------------------------
def bootstrap():
    """Initialise schema, categories and demo data (called on startup)."""
    with app.app_context():
        init_db()
        db = get_db()
        seed_categories(db)
        seed_demo_data(app.config["DATABASE"])


if os.environ.get("MEDIFINDER_SKIP_BOOTSTRAP") != "1":
    bootstrap()


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=os.environ.get("FLASK_DEBUG") == "1")
