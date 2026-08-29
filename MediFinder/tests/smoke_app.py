"""End-to-end smoke checks for MediFinder.

Run from the MediFinder directory:
    python tests/smoke_app.py

The script uses a temporary SQLite database and temporary upload directory, so
it does not alter local demo data. It checks route rendering, internal links,
core POST workflows, JSON APIs and the map/location pages that depend on
client-side JavaScript.
"""
from __future__ import annotations

import os
import sys
import tempfile
import time
from html.parser import HTMLParser
from io import BytesIO
from pathlib import Path
from urllib.parse import parse_qs, urlparse

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("MEDIFINDER_SKIP_BOOTSTRAP", "1")

from app import app  # noqa: E402
from database import close_db, get_db, init_db, seed_categories  # noqa: E402
from seed import seed_demo_data  # noqa: E402


class LinkParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links: list[str] = []
        self.forms: list[tuple[str, str]] = []

    def handle_starttag(self, tag, attrs):
        data = dict(attrs)
        if tag == "a" and data.get("href"):
            self.links.append(data["href"])
        if tag == "form":
            self.forms.append((data.get("method", "GET").upper(), data.get("action") or ""))


def assert_status(resp, label, allowed=(200, 302, 303, 401, 405)):
    assert resp.status_code in allowed, f"{label}: unexpected HTTP {resp.status_code}\n{resp.get_data(as_text=True)[:600]}"
    return resp


def setup_temp_app(tmp: str):
    app.config.update(
        TESTING=True,
        DATABASE=os.path.join(tmp, "medifinder-smoke.db"),
        UPLOAD_FOLDER=os.path.join(tmp, "uploads"),
        WTF_CSRF_ENABLED=False,
    )
    os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)
    with app.app_context():
        init_db()
        seed_categories(get_db())
        seed_demo_data(app.config["DATABASE"])
        close_db(None)


def db_row(query: str, args=()):
    with app.app_context():
        row = get_db().execute(query, args).fetchone()
        close_db(None)
        return row


def db_value(query: str, args=()):
    row = db_row(query, args)
    return row[0] if row else None


def walk_internal_links(rendered_pages: list[str]):
    client = app.test_client()
    checked: set[str] = set()
    skipped_prefixes = ("#", "mailto:", "tel:", "javascript:")
    for html in rendered_pages:
        parser = LinkParser()
        parser.feed(html)
        for href in parser.links:
            href = href.strip()
            if not href or href.startswith(skipped_prefixes):
                continue
            parsed = urlparse(href)
            if parsed.scheme in {"http", "https"} or parsed.netloc:
                continue
            if parsed.path.startswith("/uploads/"):
                continue
            path = parsed.path or "/"
            if parsed.query:
                path += "?" + parsed.query
            if path in checked:
                continue
            checked.add(path)
            resp = client.get(path, follow_redirects=False)
            assert resp.status_code != 404, f"Broken internal link: {href} -> 404"
            assert resp.status_code < 500, f"Internal link crashed: {href} -> {resp.status_code}"
    return checked


def assert_login_cookie_modes():
    """Regression coverage for local and Arena live-preview login cookies."""
    shop = db_row("SELECT name FROM shops WHERE status='Verified' ORDER BY id LIMIT 1")
    assert shop, "Seeded verified shop missing"
    flows = [
        ("/account/login", {"email": "demo@medifinder.app", "password": "demo1234"}, "/account", "Pickup holds"),
        ("/pharmacy/login", {"username": shop["name"], "password": "demo1234"}, "/pharmacy/dashboard", "Pharmacy operations"),
        ("/admin", {"username": "admin", "password": "admin123"}, "/admin/dashboard", "Admin console"),
    ]

    for login_path, credentials, protected_path, expected_text in flows:
        # Normal local development should keep simple Lax cookies.
        local = app.test_client()
        resp = local.post(login_path, data=credentials, follow_redirects=False)
        cookie = resp.headers.get("Set-Cookie", "")
        assert resp.status_code == 302, f"{login_path} local login did not redirect"
        assert "SameSite=Lax" in cookie, f"{login_path} local cookie should be SameSite=Lax: {cookie}"
        assert "Secure" not in cookie, f"{login_path} local cookie should not be Secure: {cookie}"
        protected = local.get(protected_path)
        assert protected.status_code == 200 and expected_text in protected.get_data(as_text=True), f"{protected_path} local session failed"

        # Arena/browser preview is HTTPS and may be embedded. Cookie must survive
        # the post-login redirect there too.
        preview = app.test_client()
        resp = preview.post(login_path, data=credentials, follow_redirects=False, base_url="https://5000-test.e2b.app")
        cookie = resp.headers.get("Set-Cookie", "")
        assert resp.status_code == 302, f"{login_path} preview login did not redirect"
        assert "SameSite=None" in cookie and "Secure" in cookie, f"{login_path} preview cookie not iframe-safe: {cookie}"
        protected = preview.get(protected_path, base_url="https://5000-test.e2b.app")
        assert protected.status_code == 200 and expected_text in protected.get_data(as_text=True), f"{protected_path} preview session failed"

    # Some proxies forward an internal Host but a non-loopback remote address.
    # That still represents the user's HTTPS preview, so it must get safe cookies.
    proxy = app.test_client()
    resp = proxy.post(
        "/admin",
        data={"username": "admin", "password": "admin123"},
        follow_redirects=False,
        base_url="https://internal-preview.local",
        environ_overrides={"REMOTE_ADDR": "10.12.0.46"},
    )
    cookie = resp.headers.get("Set-Cookie", "")
    assert "SameSite=None" in cookie and "Secure" in cookie, f"proxied preview cookie not safe: {cookie}"

    # If the browser blocks preview cookies completely, admin login should still
    # land on the dashboard through the short-lived signed fallback token.
    blocked = app.test_client()
    resp = blocked.post(
        "/admin",
        data={"username": "admin", "password": "admin123"},
        follow_redirects=False,
        base_url="http://127.0.0.1:5000",
        environ_overrides={"REMOTE_ADDR": "10.12.0.46"},
    )
    location = resp.headers.get("Location", "")
    token = parse_qs(urlparse(location).query).get("admin_token", [""])[0]
    assert resp.status_code == 302 and token, f"cookie-blocked admin login did not issue fallback token: {location}"
    fresh_no_cookie = app.test_client()
    dash = fresh_no_cookie.get(location, environ_overrides={"REMOTE_ADDR": "10.12.0.46"})
    html = dash.get_data(as_text=True)
    assert dash.status_code == 200 and "Admin console" in html, "cookie-blocked admin token did not open dashboard"
    assert 'name="admin_token"' in html, "admin dashboard forms did not preserve fallback token"

    verified_id = db_value("SELECT id FROM shops WHERE status='Verified' ORDER BY id LIMIT 1")
    assert verified_id, "No verified pharmacy available for admin token action test"
    suspend = fresh_no_cookie.post(
        f"/admin/shop/{verified_id}/suspend",
        data={"admin_token": token, "note": "cookie blocked smoke"},
        follow_redirects=False,
        environ_overrides={"REMOTE_ADDR": "10.12.0.46"},
    )
    assert suspend.status_code == 302 and "admin_token=" in suspend.headers.get("Location", ""), "admin token was not preserved after action"
    assert db_value("SELECT status FROM shops WHERE id=?", (verified_id,)) == "Suspended"
    reinstate = fresh_no_cookie.post(
        f"/admin/shop/{verified_id}/reinstate",
        data={"admin_token": token},
        follow_redirects=False,
        environ_overrides={"REMOTE_ADDR": "10.12.0.46"},
    )
    assert reinstate.status_code == 302 and "admin_token=" in reinstate.headers.get("Location", ""), "admin token was not preserved after reinstate"
    assert db_value("SELECT status FROM shops WHERE id=?", (verified_id,)) == "Verified"


def assert_logic_edge_cases():
    """Check defensive branches that used to be easy to miss manually."""
    # Stale/deleted session IDs should never crash protected pages or APIs.
    stale_customer = app.test_client()
    with stale_customer.session_transaction() as sess:
        sess["customer_id"] = 999999
    resp = stale_customer.get("/account", follow_redirects=False)
    assert resp.status_code == 302 and "/account/login" in resp.headers.get("Location", "")
    resp = stale_customer.get("/api/favourites")
    assert resp.status_code == 401 and resp.get_json()["ok"] is False

    stale_shop = app.test_client()
    with stale_shop.session_transaction() as sess:
        sess["shop_id"] = 999999
    resp = stale_shop.get("/pharmacy/dashboard", follow_redirects=False)
    assert resp.status_code == 302 and "/pharmacy/login" in resp.headers.get("Location", "")

    # Input coercion should return useful 4xx/2xx responses, never 500s.
    client = app.test_client()
    item = db_row("SELECT id FROM inventory WHERE stock_quantity > 5 LIMIT 1")
    assert item, "No inventory available for edge-case reserve test"
    reserve = client.post("/api/reserve", json={"med_id": item["id"], "phone": "+919111111111", "quantity": "abc"})
    reserve_json = reserve.get_json()
    assert reserve.status_code == 200 and reserve_json["ok"] and reserve_json["reservation_id"]
    nearby = client.get("/api/shops/nearby?lat=0&lng=0")
    assert nearby.status_code == 200 and nearby.get_json()["ok"] is True

    with app.app_context():
        db = get_db()
        shop_id = db.execute("SELECT id FROM shops WHERE status='Verified' LIMIT 1").fetchone()["id"]
        cur = db.execute(
            "INSERT INTO inventory (shop_id, med_name, salt_composition, price, mrp, stock_quantity, dosage, is_active) "
            "VALUES (?, 'One Stock Smoke', 'Smoke', 1, 1, 1, '1mg', 1)",
            (shop_id,),
        )
        limited_item_id = cur.lastrowid
        db.commit()
        close_db(None)
    first_hold = client.post("/api/reserve", json={"med_id": limited_item_id, "phone": "+919111111112", "quantity": 1})
    assert first_hold.status_code == 200 and first_hold.get_json()["ok"] is True
    overbook = client.post("/api/reserve", json={"med_id": limited_item_id, "phone": "+919111111113", "quantity": 1})
    assert overbook.status_code == 400 and overbook.get_json()["ok"] is False

    customer = app.test_client()
    assert_status(customer.post("/account/login", data={"email": "demo@medifinder.app", "password": "demo1234"}, follow_redirects=False), "edge customer login", allowed=(302,))
    review = customer.post("/api/shops/1/review", json={"rating": "abc", "comment": "bad input"})
    assert review.status_code == 400 and review.get_json()["ok"] is False

    # Customer next redirects should not allow external URLs.
    redirect_test = app.test_client()
    resp = redirect_test.post("/account/login?next=https://evil.example", data={"email": "demo@medifinder.app", "password": "demo1234"}, follow_redirects=False)
    assert resp.status_code == 302 and resp.headers.get("Location") == "/account"


def main():
    with tempfile.TemporaryDirectory(prefix="medifinder-smoke-") as tmp:
        setup_temp_app(tmp)
        rendered: list[str] = []

        # Public route rendering, including all map/location pages.
        client = app.test_client()
        public_routes = [
            "/",
            "/map",
            "/map?city=Patna",
            "/search?q=Dolo&city=Patna&dosage=650&quantity=2&lat=25.611&lng=85.143",
            "/prescription",
            "/account/login",
            "/account/register",
            "/pharmacy/login",
            "/pharmacy/register",
            "/admin",
            "/pharmacy/1",
        ]
        for route in public_routes:
            resp = assert_status(client.get(route), route, allowed=(200, 302))
            if resp.status_code == 200:
                rendered.append(resp.get_data(as_text=True))

        home_html = rendered[0]
        assert 'id="home-map"' in home_html and "locateBtn" in home_html, "Homepage map or auto-location control missing"
        map_html = client.get("/map").get_data(as_text=True)
        assert 'id="pharmacy-map"' in map_html and "mapAutoLocate" in map_html
        search_html = client.get("/search").get_data(as_text=True)
        assert 'id="map"' in search_html and "locateBtn" in search_html and "mapLocateBtn" in search_html
        rx_html = client.get("/prescription").get_data(as_text=True)
        assert "rxLocate" in rx_html
        assert_login_cookie_modes()
        assert_logic_edge_cases()

        # JSON APIs.
        resp = assert_status(client.get("/api/autocomplete?q=do"), "/api/autocomplete", allowed=(200,))
        assert isinstance(resp.get_json(), list)
        resp = assert_status(client.get("/api/search?q=Dolo&city=Patna&dosage=650&quantity=2&lat=25.611&lng=85.143"), "/api/search", allowed=(200,))
        data = resp.get_json()
        assert data["ok"] and data["count"] >= 1 and data["requested_quantity"] == 2
        resp = assert_status(client.get("/api/shops/nearby?lat=25.611&lng=85.143"), "/api/shops/nearby", allowed=(200,))
        assert resp.get_json()["ok"] and len(resp.get_json()["shops"]) >= 1
        resp = assert_status(client.get("/api/location/estimate?city=Patna"), "/api/location/estimate", allowed=(200,))
        loc = resp.get_json()
        assert loc["ok"] and loc["lat"] and loc["lng"] and loc["approximate"] is True

        # Customer login, favourites, reservation, cancellation, review, prescription upload.
        customer = app.test_client()
        assert_status(customer.post("/account/login", data={"email": "demo@medifinder.app", "password": "demo1234"}, follow_redirects=False), "customer login", allowed=(302,))
        item = db_row("SELECT id, shop_id FROM inventory WHERE med_name LIKE 'Dolo%' AND stock_quantity > 5 LIMIT 1")
        assert item, "Seeded Dolo inventory missing"
        reserve = customer.post("/api/reserve", json={"med_id": item["id"], "phone": "+919999999999", "name": "Smoke Patient", "quantity": 1})
        assert reserve.status_code == 200 and reserve.get_json()["ok"], reserve.get_data(as_text=True)
        rid_cancel = reserve.get_json()["reservation_id"]
        assert_status(customer.post(f"/account/reservation/{rid_cancel}/cancel", follow_redirects=False), "cancel reservation", allowed=(302,))
        fav = customer.post("/api/favourites", json={"med_name": "Dolo 650", "salt": "Paracetamol"})
        assert fav.status_code in (200, 409)
        assert_status(customer.delete("/api/favourites", json={"med_name": "Dolo 650", "salt": "Paracetamol"}), "delete favourite", allowed=(200,))
        fav_form = customer.post("/api/favourites", json={"med_name": "Crocin 650", "salt": "Paracetamol"})
        assert fav_form.status_code in (200, 409)
        fav_id = db_value("SELECT id FROM favourites WHERE med_name='Crocin 650' ORDER BY id DESC LIMIT 1")
        assert fav_id
        assert_status(customer.post("/api/favourites", data={"id": fav_id}, follow_redirects=False), "form delete favourite", allowed=(302,))
        assert db_value("SELECT COUNT(*) FROM favourites WHERE id=?", (fav_id,)) == 0
        review = customer.post(f"/api/shops/{item['shop_id']}/review", json={"rating": 5, "comment": "Smoke test review"})
        assert review.status_code == 200 and review.get_json()["ok"]
        rx = customer.post(
            "/prescription",
            data={
                "name": "Smoke Patient",
                "phone": "+919999999999",
                "city": "Patna",
                "note": "Smoke upload",
                "prescription_file": (BytesIO(b"%PDF-1.4 smoke"), "smoke-rx.pdf"),
            },
            content_type="multipart/form-data",
            follow_redirects=False,
        )
        assert_status(rx, "prescription upload", allowed=(302,))
        rx_id = db_value("SELECT id FROM prescription_requests WHERE customer_phone=? ORDER BY id DESC LIMIT 1", ("+919999999999",))
        assert rx_id, "Prescription upload was not inserted"
        account = assert_status(customer.get("/account"), "account", allowed=(200,))
        rendered.append(account.get_data(as_text=True))

        # Pharmacy login, add/update/delete inventory, profile save and reservation actions.
        shop = db_row("SELECT id, name FROM shops WHERE status='Verified' ORDER BY id LIMIT 1")
        shop_client = app.test_client()
        assert_status(shop_client.post("/pharmacy/login", data={"username": shop["name"], "password": "demo1234"}, follow_redirects=False), "shop login", allowed=(302,))
        dash = assert_status(shop_client.get("/pharmacy/dashboard"), "shop dashboard", allowed=(200,))
        rendered.append(dash.get_data(as_text=True))
        unique_med = f"SmokeMed {int(time.time())}"
        assert_status(shop_client.post("/pharmacy/inventory/add", data={
            "med_name": unique_med,
            "salt_composition": "Smoke Salt",
            "category_id": "1",
            "manufacturer": "Smoke Labs",
            "batch_no": "SMK1",
            "expiry_date": "2027-12-31",
            "mrp": "12.50",
            "price": "10.00",
            "stock_quantity": "9",
            "dosage": "10mg",
        }, follow_redirects=False), "add inventory", allowed=(302,))
        new_item_id = db_value("SELECT id FROM inventory WHERE med_name=?", (unique_med,))
        assert new_item_id, "Inventory add did not insert item"
        upd = shop_client.post(f"/pharmacy/inventory/{new_item_id}/update", json={"stock_quantity": 7, "price": 9.5})
        assert upd.status_code == 200 and upd.get_json()["ok"]
        assert_status(shop_client.post(f"/pharmacy/inventory/{new_item_id}/delete", follow_redirects=False), "delete inventory", allowed=(302,))
        assert_status(shop_client.post("/pharmacy/profile", data={
            "name": shop["name"], "phone": "+919800011111", "email": "apollo@medifinder.demo",
            "owner_name": "Smoke Owner", "description": "Updated in smoke test",
            "address": "Frazer Road", "city": "Patna", "state": "Bihar", "pincode": "800001",
            "open_time": "08:00", "close_time": "23:00", "lat": "25.611000", "lng": "85.143000",
            "delivery": "1",
        }, follow_redirects=False), "shop profile update", allowed=(302,))

        # Reservation actions: confirm/collect and cancel.
        item2 = db_row("SELECT id FROM inventory WHERE shop_id=? AND stock_quantity > 5 LIMIT 1", (shop["id"],))
        reserve2 = customer.post("/api/reserve", json={"med_id": item2["id"], "phone": "+919888888888", "name": "Pickup Smoke", "quantity": 1})
        rid_collect = reserve2.get_json()["reservation_id"]
        stock_before_collect = db_value("SELECT stock_quantity FROM inventory WHERE id=?", (item2["id"],))
        assert_status(shop_client.post(f"/pharmacy/reservation/{rid_collect}/confirm", follow_redirects=False), "confirm reservation", allowed=(302,))
        assert_status(shop_client.post(f"/pharmacy/reservation/{rid_collect}/collect", follow_redirects=False), "collect reservation", allowed=(302,))
        stock_after_collect = db_value("SELECT stock_quantity FROM inventory WHERE id=?", (item2["id"],))
        assert stock_after_collect == stock_before_collect - 1, "Collect should decrement stock once"
        repeat_collect = shop_client.post(f"/pharmacy/reservation/{rid_collect}/collect", json={})
        assert repeat_collect.status_code == 400 and repeat_collect.get_json()["ok"] is False
        assert db_value("SELECT stock_quantity FROM inventory WHERE id=?", (item2["id"],)) == stock_after_collect, "Repeated collect must not decrement stock again"
        customer_cancel_collected = customer.post(f"/account/reservation/{rid_collect}/cancel", follow_redirects=False)
        assert customer_cancel_collected.status_code == 302
        assert db_value("SELECT status FROM reservations WHERE id=?", (rid_collect,)) == "Collected"
        reserve3 = customer.post("/api/reserve", json={"med_id": item2["id"], "phone": "+919777777777", "name": "Cancel Smoke", "quantity": 1})
        rid_shop_cancel = reserve3.get_json()["reservation_id"]
        assert_status(shop_client.post(f"/pharmacy/reservation/{rid_shop_cancel}/cancel", follow_redirects=False), "shop cancel reservation", allowed=(302,))

        # Admin auth and moderation actions, including prescription status workflow.
        admin = app.test_client()
        assert_status(admin.post("/admin", data={"username": "admin", "password": "admin123"}, follow_redirects=False), "admin login", allowed=(302,))
        admin_dash = assert_status(admin.get("/admin/dashboard"), "admin dashboard", allowed=(200,))
        rendered.append(admin_dash.get_data(as_text=True))
        for action in ("review", "match", "close"):
            assert_status(admin.post(f"/admin/prescription/{rx_id}/{action}", follow_redirects=False), f"admin prescription {action}", allowed=(302,))

        def register_pending(name: str):
            reg = app.test_client()
            resp = reg.post("/pharmacy/register", data={
                "name": name,
                "owner_name": "Smoke Pharmacist",
                "email": f"{name.lower().replace(' ', '')}@example.test",
                "phone": "+919666666666",
                "description": "Smoke pharmacy",
                "address": "Smoke Road",
                "city": "Patna",
                "state": "Bihar",
                "pincode": "800001",
                "license_number": f"DL-SMOKE-{name[-1]}",
                "password": "demo1234",
                "license_image": (BytesIO(b"fake png"), f"{name}.png"),
                "shop_photo": (BytesIO(b"fake png"), f"{name}-front.png"),
            }, content_type="multipart/form-data", follow_redirects=False)
            assert_status(resp, f"register {name}", allowed=(302,))
            return db_value("SELECT id FROM shops WHERE name=?", (name,))

        approved_id = register_pending("Smoke Pharmacy A")
        rejected_id = register_pending("Smoke Pharmacy B")
        pending_login = app.test_client()
        assert_status(pending_login.post("/pharmacy/login", data={"username": "Smoke Pharmacy A", "password": "demo1234"}, follow_redirects=False), "pending shop login", allowed=(302,))
        assert_status(pending_login.get("/pharmacy/dashboard"), "pending shop dashboard", allowed=(200,))
        assert_status(admin.post(f"/admin/shop/{approved_id}/approve", follow_redirects=False), "admin approve", allowed=(302,))
        assert_status(admin.post(f"/admin/shop/{approved_id}/suspend", data={"note": "smoke"}, follow_redirects=False), "admin suspend", allowed=(302,))
        suspended_session = pending_login.get("/pharmacy/dashboard", follow_redirects=False)
        assert suspended_session.status_code == 302 and "/pharmacy/login" in suspended_session.headers.get("Location", "")
        suspended_login = app.test_client().post("/pharmacy/login", data={"username": "Smoke Pharmacy A", "password": "demo1234"}, follow_redirects=False)
        assert suspended_login.status_code == 200, "Suspended shop should be held on login page"
        assert_status(admin.post(f"/admin/shop/{approved_id}/reinstate", follow_redirects=False), "admin reinstate", allowed=(302,))
        assert_status(admin.post(f"/admin/shop/{rejected_id}/reject", data={"note": "smoke reject"}, follow_redirects=False), "admin reject", allowed=(302,))
        assert_status(admin.post(f"/admin/shop/{rejected_id}/delete", follow_redirects=False), "admin delete", allowed=(302,))

        # Internal links from representative pages should resolve.
        checked = walk_internal_links(rendered + [map_html, search_html, rx_html])

        print("MediFinder smoke checks passed")
        print(f"Routes/pages rendered: {len(public_routes) + 3}")
        print(f"Internal links checked: {len(checked)}")
        print("Workflows checked: local/preview cookies, customer/pharmacy/admin login, location-map pages, search APIs, reserve/cancel/collect, favourites, reviews, prescription upload/status, inventory CRUD, shop profile, admin moderation")


if __name__ == "__main__":
    main()
