import io
import os
import shutil
import sqlite3
import sys
import tempfile
import unittest

MEDI_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if MEDI_DIR not in sys.path:
    sys.path.insert(0, MEDI_DIR)

import app as medifinder_app  # noqa: E402


PNG_BYTES = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc\xf8\xcf\xc0"
    b"\x00\x00\x03\x01\x01\x00\xc9\xfe\x92\xef\x00\x00\x00\x00IEND\xaeB`\x82"
)


class MediFinderAppTestCase(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp(prefix="medifinder_test_")
        self.db_path = os.path.join(self.tmpdir, "test.db")
        self.upload_dir = os.path.join(self.tmpdir, "uploads")
        os.makedirs(self.upload_dir, exist_ok=True)

        self.orig_db = medifinder_app.app.config["DATABASE"]
        self.orig_uploads = medifinder_app.app.config["UPLOAD_FOLDER"]

        medifinder_app.app.config.update(
            TESTING=True,
            DATABASE=self.db_path,
            UPLOAD_FOLDER=self.upload_dir,
        )
        medifinder_app.init_db()
        self.client = medifinder_app.app.test_client()

    def tearDown(self):
        medifinder_app.app.config.update(
            TESTING=False,
            DATABASE=self.orig_db,
            UPLOAD_FOLDER=self.orig_uploads,
        )
        shutil.rmtree(self.tmpdir, ignore_errors=True)

    def _register_and_verify_shop(self, name="City Medico", password="secret", city="Patna", lat=25.60, lng=85.14):
        resp = self.client.post(
            "/register",
            data={
                "name": name,
                "password": password,
                "license_number": "DL-998877",
                "phone": "9876543210",
                "opening_hours": "8 AM - 10 PM",
                "license_image": (io.BytesIO(PNG_BYTES), "license.png"),
                "shop_photo": (io.BytesIO(PNG_BYTES), "front.png"),
            },
            content_type="multipart/form-data",
            follow_redirects=False,
        )
        self.assertEqual(resp.status_code, 302)
        self.assertIn("/dashboard", resp.headers["Location"])

        # Update location while logged in as shop
        loc_resp = self.client.post(
            "/update_location",
            data={
                "city": city,
                "lat": str(lat),
                "lng": str(lng),
                "phone": "9876543210",
                "opening_hours": "8 AM - 10 PM",
            },
            follow_redirects=False,
        )
        self.assertEqual(loc_resp.status_code, 302)

        with sqlite3.connect(self.db_path) as conn:
            shop_id = conn.execute("SELECT id FROM shops WHERE name = ?", (name,)).fetchone()[0]

        # Admin login & approve
        admin_login = self.client.post(
            "/admin",
            data={"username": medifinder_app.ADMIN_USERNAME, "password": os.environ.get("ADMIN_PASS", "admin123")},
            follow_redirects=False,
        )
        self.assertEqual(admin_login.status_code, 302)
        approve_resp = self.client.post(f"/approve/{shop_id}", follow_redirects=False)
        self.assertEqual(approve_resp.status_code, 302)
        return shop_id

    def test_public_pages_and_existing_ui_hooks_preserved(self):
        for path in ("/", "/login", "/register", "/admin"):
            res = self.client.get(path)
            self.assertEqual(res.status_code, 200, f"GET {path} failed")
            html = res.get_data(as_text=True)
            self.assertIn('name="viewport"', html, f"Viewport meta missing on {path}")
            self.assertIn("toggleTheme()", html, f"Theme toggle missing on {path}")

        home_html = self.client.get("/").get_data(as_text=True)
        self.assertIn('id="search-form"', home_html)
        self.assertIn('id="query-input"', home_html)
        self.assertIn('id="city-input"', home_html)
        self.assertIn('onclick="detectUserLocation()"', home_html)
        self.assertIn('id="map"', home_html)
        self.assertIn('id="holdModal"', home_html)

    def test_end_to_end_inventory_search_distance_sort_and_hold_lifecycle(self):
        self._register_and_verify_shop("Near Pharmacy", "pw1", "Patna", 25.5950, 85.1380)
        self.client.post(
            "/dashboard",
            data={
                "med_name": "Dolo 650",
                "salt_composition": "Paracetamol",
                "dosage": "650mg Strip",
                "price": "32.50",
                "stock_quantity": "3",
            },
        )
        self.client.get("/logout")

        self._register_and_verify_shop("Far Pharmacy", "pw2", "Patna", 25.6500, 85.2100)
        self.client.post(
            "/dashboard",
            data={
                "med_name": "Calpol 650",
                "salt_composition": "Paracetamol",
                "dosage": "650mg Strip",
                "price": "28.00",
                "stock_quantity": "5",
            },
        )

        # Search by generic salt with user coordinates -> nearest first
        search_res = self.client.get("/api/search?query=paracetamol&city=Patna&lat=25.5941&lng=85.1376")
        self.assertEqual(search_res.status_code, 200)
        items = search_res.get_json()
        self.assertEqual(len(items), 2)
        self.assertEqual(items[0]["shop_name"], "Near Pharmacy")
        self.assertEqual(items[0]["med_id"], items[0]["id"])
        self.assertIsNotNone(items[0]["distance_km"])
        self.assertLess(items[0]["distance_km"], items[1]["distance_km"])

        # Sort by price_asc -> Far Pharmacy (28.00) comes first
        price_res = self.client.get("/api/search?query=paracetamol&sort=price_asc")
        price_items = price_res.get_json()
        self.assertEqual(price_items[0]["shop_name"], "Far Pharmacy")

        med_id = items[0]["med_id"]

        # Invalid phone rejected
        bad_hold = self.client.post("/api/reserve", json={"med_id": med_id, "phone": "123"})
        self.assertEqual(bad_hold.status_code, 400)

        # Valid 2-unit hold succeeds
        ok_hold = self.client.post(
            "/api/reserve",
            json={"med_id": med_id, "phone": "9876543210", "customer_name": "Aman", "quantity": 2},
        )
        self.assertEqual(ok_hold.status_code, 200)
        hold_payload = ok_hold.get_json()
        self.assertTrue(hold_payload["success"])
        self.assertEqual(hold_payload["available_quantity"], 1)
        res_id = hold_payload["reservation_id"]

        # Over-holding beyond remaining 1 unit is blocked
        over_hold = self.client.post("/api/reserve", json={"med_id": med_id, "phone": "9876543211", "quantity": 2})
        self.assertEqual(over_hold.status_code, 400)

        # Log back into Near Pharmacy and mark hold Picked Up -> stock_quantity drops from 3 to 1
        self.client.get("/logout")
        self.client.post("/login", data={"username": "Near Pharmacy", "password": "pw1"})
        complete_res = self.client.post(f"/reservation/{res_id}/complete", follow_redirects=False)
        self.assertEqual(complete_res.status_code, 302)

        after_items = self.client.get("/api/search?query=Dolo").get_json()
        self.assertEqual(after_items[0]["stock_quantity"], 1)
        self.assertEqual(after_items[0]["available_quantity"], 1)

        # Inline medicine update works
        self.client.post(
            f"/update_medicine/{med_id}",
            data={
                "med_name": "Dolo 650",
                "salt_composition": "Paracetamol",
                "dosage": "650mg / 15 Tabs",
                "price": "34.00",
                "stock_quantity": "12",
            },
        )
        updated = self.client.get("/api/search?query=Dolo").get_json()[0]
        self.assertEqual(updated["price"], 34.0)
        self.assertEqual(updated["stock_quantity"], 12)

    def test_stale_holds_auto_expire_after_two_hours(self):
        self._register_and_verify_shop("Expiry Medico", "pw", "Patna", 25.60, 85.14)
        self.client.post(
            "/dashboard",
            data={"med_name": "Azithral 500", "salt_composition": "Azithromycin", "price": "110", "stock_quantity": "1"},
        )
        med_id = self.client.get("/api/search?query=Azithral").get_json()[0]["med_id"]

        hold_res = self.client.post("/api/reserve", json={"med_id": med_id, "phone": "9988776655", "quantity": 1})
        self.assertEqual(hold_res.status_code, 200)
        res_id = hold_res.get_json()["reservation_id"]

        # Currently 0 available
        self.assertEqual(self.client.get("/api/search?query=Azithral").get_json()[0]["available_quantity"], 0)
        self.assertEqual(len(self.client.get("/api/search?query=Azithral&in_stock=1").get_json()), 0)

        # Backdate reservation past 2 hours -> auto-expires on next search/reserve
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "UPDATE reservations SET created_at = datetime('now', '-3 hours'), expires_at = datetime('now', '-1 hour') WHERE id = ?",
                (res_id,),
            )
            conn.commit()

        refreshed = self.client.get("/api/search?query=Azithral&in_stock=1").get_json()
        self.assertEqual(len(refreshed), 1)
        self.assertEqual(refreshed[0]["available_quantity"], 1)

    def test_upload_collision_protection_and_duplicate_shop_prevention(self):
        self._register_and_verify_shop("UniqueCare", "pw1")
        self.client.get("/logout")

        dup_resp = self.client.post(
            "/register",
            data={
                "name": "uniquecare",
                "password": "pw2",
                "license_number": "DL-2",
                "license_image": (io.BytesIO(PNG_BYTES), "license.png"),
                "shop_photo": (io.BytesIO(PNG_BYTES), "front.png"),
            },
            content_type="multipart/form-data",
        )
        self.assertIn("already registered", dup_resp.get_data(as_text=True))

    def test_existing_repository_database_migration_preserves_all_records(self):
        real_db = os.path.join(MEDI_DIR, "database.db")
        if not os.path.exists(real_db):
            self.skipTest("No repository database.db found")

        copied_db = os.path.join(self.tmpdir, "copied_prod.db")
        shutil.copy2(real_db, copied_db)

        with sqlite3.connect(copied_db) as conn:
            before_shops = conn.execute("SELECT COUNT(*) FROM shops").fetchone()[0]
            before_inv = conn.execute("SELECT COUNT(*) FROM inventory").fetchone()[0]

        medifinder_app._initialized_dbs.discard(copied_db)
        medifinder_app.app.config["DATABASE"] = copied_db
        medifinder_app.init_db()

        with sqlite3.connect(copied_db) as conn:
            after_shops = conn.execute("SELECT COUNT(*) FROM shops").fetchone()[0]
            after_inv = conn.execute("SELECT COUNT(*) FROM inventory").fetchone()[0]

        self.assertEqual(before_shops, after_shops)
        self.assertEqual(before_inv, after_inv)

        # Existing Aspirin records from Verified Apollo shops appear in search with non-zero prices
        aspirin_results = self.client.get("/api/search?query=Aspirin&lat=25.5941&lng=85.1376").get_json()
        self.assertGreaterEqual(len(aspirin_results), 2)
        for item in aspirin_results:
            self.assertGreater(float(item["price"]), 0.0)

        with sqlite3.connect(copied_db) as conn:
            zero_priced = conn.execute("SELECT COUNT(*) FROM inventory WHERE price IS NULL OR price <= 0").fetchone()[0]
        self.assertEqual(zero_priced, 0, "All medicines in database.db should have positive prices")

        # Legacy plaintext shop login works and transparently upgrades hash
        login_res = self.client.post("/login", data={"username": "Allentra", "password": "12345"}, follow_redirects=False)
        self.assertEqual(login_res.status_code, 302)
        with sqlite3.connect(copied_db) as conn:
            upgraded_pw = conn.execute("SELECT password FROM shops WHERE name = 'Allentra'").fetchone()[0]
        self.assertTrue(upgraded_pw.startswith(("scrypt:", "pbkdf2:")))

    def test_no_blocked_osm_tile_urls_or_unpkg_leaflet_in_frontend(self):
        main_js_path = os.path.join(MEDI_DIR, "static", "js", "main.js")
        index_tpl_path = os.path.join(MEDI_DIR, "templates", "index.html")
        dashboard_tpl_path = os.path.join(MEDI_DIR, "templates", "dashboard.html")

        for fpath in (main_js_path, dashboard_tpl_path):
            with open(fpath, encoding="utf-8") as fh:
                content = fh.read()
            self.assertNotIn("tile.openstreetmap.org", content, f"Blocked OSM tile server still referenced in {fpath}")
            self.assertNotIn("geojs.io", content, f"Inaccurate IP geolocation should not be used in {fpath}")
            self.assertNotIn("ipwho.is", content, f"Inaccurate IP geolocation should not be used in {fpath}")
            self.assertIn("attachResilientTileLayer", content)

        for tpl_path in (index_tpl_path, dashboard_tpl_path):
            with open(tpl_path, encoding="utf-8") as fh:
                tpl_content = fh.read()
            self.assertNotIn("unpkg.com", tpl_content, f"External unpkg CDN still referenced in {tpl_path}")
            self.assertIn("/static/vendor/leaflet/leaflet.js", tpl_content)
            self.assertIn("/static/vendor/leaflet/leaflet.css", tpl_content)

        # Verify local Leaflet assets and /static/js/main.js serve with HTTP 200
        for asset_url in ("/static/vendor/leaflet/leaflet.js", "/static/vendor/leaflet/leaflet.css"):
            with self.client.get(asset_url) as asset_res:
                self.assertEqual(asset_res.status_code, 200)
        with self.client.get("/static/js/main.js") as js_res:
            self.assertEqual(js_res.status_code, 200)
            self.assertIn("no-store", js_res.headers.get("Cache-Control", ""))

    def test_comma_separated_area_city_search_and_map_directions_hooks(self):
        self._register_and_verify_shop(name="Boring Road Chemist", city="Patna", lat=25.6100, lng=85.1200)
        self.client.post(
            "/dashboard",
            data={
                "med_name": "Dolo 650",
                "salt_composition": "Paracetamol",
                "dosage": "650mg Strip",
                "price": "32.00",
                "stock_quantity": "20",
            },
            follow_redirects=False,
        )

        # Comma-separated Area, City ("Boring Road, Patna") in #city-input matches Patna pharmacies even without lat/lng
        res_no_gps = self.client.get("/api/search?query=Dolo+650&city=Boring+Road%2C+Patna")
        self.assertEqual(res_no_gps.status_code, 200)
        self.assertEqual(len(res_no_gps.get_json()), 1)

        # And with lat/lng, distance_km is also computed
        res = self.client.get("/api/search?query=Dolo+650&city=Boring+Road%2C+Patna&lat=25.6148&lng=85.1125")
        self.assertEqual(res.status_code, 200)
        items = res.get_json()
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["shop_name"], "Boring Road Chemist")
        self.assertIsNotNone(items[0]["distance_km"])

        # Suburb name ("Gola Road, Danapur") with Danapur GPS coordinates finds nearby verified Patna/Danapur shops within 25 km
        res_danapur = self.client.get("/api/search?query=Dolo+650&city=Gola+Road%2C+Danapur&lat=25.6142&lng=85.0648")
        self.assertEqual(res_danapur.status_code, 200)
        danapur_items = res_danapur.get_json()
        self.assertEqual(len(danapur_items), 1)
        self.assertIsNotNone(danapur_items[0]["distance_km"])

        # Verify in-map route banner, public-API UI widgets, and high-accuracy watchPosition hooks exist
        home_html = self.client.get("/").get_data(as_text=True)
        for hook in (
            "route-info-banner",
            "route-distance-text",
            "route-duration-text",
            "clearMapRoute()",
            "gps-iframe-notice",
            "location-suggestions",
            "local-env-bar",
            "medInfoModal",
        ):
            self.assertIn(hook, home_html)
        with self.client.get("/static/js/main.js") as js_res:
            js_text = js_res.get_data(as_text=True)
        for fn_hook in (
            "showDirectionsOnMap",
            "renderRouteOnMap",
            "clearMapRoute",
            "placeOrUpdateUserMarker",
            "watchPosition",
            "fetchPlaceSuggestions",
            "resolveIndianPincodeLabel",
            "updateLocalEnvironmentBar",
            "openMedicineInfoModal",
            "fetchRxNormSpellingSuggestions",
            "autoFillSaltFromRxNorm",
        ):
            self.assertIn(fn_hook, js_text)
        self.assertNotIn("/api/client-location", js_text)


if __name__ == "__main__":
    unittest.main()
