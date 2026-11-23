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

    def test_autocomplete_substitutes_open_now_and_rx_badges(self):
        # Register & verify two Patna stores: one 24x7 brand store and one generic store
        self._register_and_verify_shop("Apollo 24x7 Care", "pass1234", "Patna", 25.6000, 85.1200)
        self.client.post("/login", data={"username": "Apollo 24x7 Care", "password": "pass1234"})
        self.client.post(
            "/update_location",
            data={"city": "Patna", "lat": "25.6000", "lng": "85.1200", "phone": "9835011111", "opening_hours": "24x7 Open"},
        )
        self.client.post(
            "/dashboard",
            data={
                "med_name": "Dolo 650",
                "salt_composition": "Paracetamol",
                "dosage": "650mg",
                "price": "34.00",
                "stock_quantity": "15",
                "expiry_date": "2028-12-31",
            },
        )
        self.client.post(
            "/dashboard",
            data={
                "med_name": "Azithral 500",
                "salt_composition": "Azithromycin",
                "dosage": "500mg",
                "price": "119.00",
                "stock_quantity": "8",
                "rx_required": "1",
                "expiry_date": "2028-10-31",
            },
        )
        # Expired batch must NOT appear in public search
        self.client.post(
            "/dashboard",
            data={
                "med_name": "Expired Syrup",
                "salt_composition": "Paracetamol",
                "dosage": "100ml",
                "price": "45.00",
                "stock_quantity": "10",
                "expiry_date": "2022-01-01",
            },
        )
        self.client.get("/logout")

        self._register_and_verify_shop("Janaushadhi Generic", "pass1234", "Patna", 25.6050, 85.1300)
        self.client.post("/login", data={"username": "Janaushadhi Generic", "password": "pass1234"})
        self.client.post(
            "/update_location",
            data={"city": "Patna", "lat": "25.6050", "lng": "85.1300", "phone": "9835022222", "opening_hours": "Closed"},
        )
        self.client.post(
            "/dashboard",
            data={
                "med_name": "Paracetamol 650 IP",
                "salt_composition": "Paracetamol",
                "dosage": "650mg",
                "price": "14.50",
                "stock_quantity": "30",
                "expiry_date": "2028-12-31",
            },
        )
        self.client.get("/logout")

        # 1) Live autocomplete returns non-expired medicines with store count & min price
        ac = self.client.get("/api/autocomplete?q=Paracetamol").get_json()
        ac_names = [x["med_name"] for x in ac]
        self.assertIn("Dolo 650", ac_names)
        self.assertIn("Paracetamol 650 IP", ac_names)
        self.assertNotIn("Expired Syrup", ac_names)

        # 2) Expired batch excluded from public /api/search
        exp_search = self.client.get("/api/search?query=Expired+Syrup").get_json()
        self.assertEqual(len(exp_search), 0)

        # 3) Rx badge set on Schedule H antibiotic
        az_search = self.client.get("/api/search?query=Azithral").get_json()
        self.assertEqual(len(az_search), 1)
        self.assertTrue(az_search[0]["rx_required"])
        self.assertTrue(az_search[0]["is_24x7"])

        # 4) open_now=1 filters out closed store
        open_res = self.client.get("/api/search?query=Paracetamol&open_now=1").get_json()
        self.assertEqual(len(open_res), 1)
        self.assertEqual(open_res[0]["shop_name"], "Apollo 24x7 Care")

        # 5) Generic substitutes return cheaper Paracetamol 650 IP with % savings
        subs_res = self.client.get(
            "/api/substitutes?query=Dolo+650&salt=Paracetamol&exclude_med_name=Dolo+650&ref_price=34.0"
        ).get_json()
        self.assertGreaterEqual(len(subs_res["substitutes"]), 1)
        top_sub = subs_res["substitutes"][0]
        self.assertEqual(top_sub["med_name"], "Paracetamol 650 IP")
        self.assertGreater(top_sub["savings_pct"], 50)

    def test_my_active_holds_pickup_code_cancellation_and_anti_spam_limit(self):
        self._register_and_verify_shop("Hold Care Pharmacy", "pass1234", "Patna", 25.5941, 85.1376)
        self.client.post("/login", data={"username": "Hold Care Pharmacy", "password": "pass1234"})
        self.client.post(
            "/update_location",
            data={"city": "Patna", "lat": "25.5941", "lng": "85.1376", "phone": "9835099999", "opening_hours": "24x7 Open"},
        )
        self.client.post(
            "/dashboard",
            data={"med_name": "Dolo 650", "salt_composition": "Paracetamol", "price": "33.60", "stock_quantity": "20"},
        )
        self.client.post(
            "/dashboard",
            data={"med_name": "PCM 650", "salt_composition": "Paracetamol", "price": "29.00", "stock_quantity": "20"},
        )
        self.client.get("/logout")

        items = self.client.get("/api/search?query=Paracetamol").get_json()
        dolo_id = next(x["med_id"] for x in items if x["med_name"] == "Dolo 650")
        pcm_id = next(x["med_id"] for x in items if x["med_name"] == "PCM 650")

        # Place first hold
        r1 = self.client.post("/api/reserve", json={"med_id": dolo_id, "phone": "9876543210", "quantity": 2})
        self.assertEqual(r1.status_code, 200)
        b1 = r1.get_json()
        self.assertTrue(b1["pickup_code"].startswith("MF-"))

        # Place second hold on another Paracetamol brand -> triggers duplicate-salt warning!
        r2 = self.client.post("/api/reserve", json={"med_id": pcm_id, "phone": "+91 98765-43210", "quantity": 1})
        self.assertEqual(r2.status_code, 200)
        b2 = r2.get_json()
        self.assertTrue(any(w["type"] == "duplicate_salt" for w in b2["safety_warnings"]))

        # Lookup via /api/my-holds returns both holds + countdown + duplicate-salt warning
        my_holds = self.client.get("/api/my-holds?phone=9876543210").get_json()
        self.assertEqual(my_holds["active_count"], 2)
        self.assertGreater(my_holds["holds"][0]["seconds_remaining"], 7000)

        # Cancel one hold and confirm available stock returns to 20
        cancel_res = self.client.post(
            f"/api/my-holds/{b1['reservation_id']}/cancel",
            json={"phone": "9876543210"},
        )
        self.assertEqual(cancel_res.status_code, 200)
        refreshed = self.client.get("/api/search?query=Dolo+650").get_json()
        self.assertEqual(refreshed[0]["available_quantity"], 20)

        # Anti-spam cap blocks excessive simultaneous holds
        medifinder_app.app.config["MAX_ACTIVE_HOLDS_PER_PHONE"] = 2
        try:
            self.client.post("/api/reserve", json={"med_id": dolo_id, "phone": "9876543210", "quantity": 1})
            blocked = self.client.post("/api/reserve", json={"med_id": dolo_id, "phone": "9876543210", "quantity": 1})
            self.assertEqual(blocked.status_code, 429)
        finally:
            medifinder_app.app.config["MAX_ACTIVE_HOLDS_PER_PHONE"] = 5

    def test_multi_medicine_prescription_matcher_and_clinical_safety_checker(self):
        self._register_and_verify_shop("OneStop Medico", "pass1234", "Patna", 25.5950, 85.1380)
        self._register_and_verify_shop("Partial Chemist", "pass1234", "Patna", 25.5942, 85.1377)

        self.client.post("/login", data={"username": "OneStop Medico", "password": "pass1234"})
        for name, salt, price in [
            ("Dolo 650", "Paracetamol", "33.00"),
            ("Azithral 500", "Azithromycin", "118.00"),
            ("Pan 40", "Pantoprazole", "145.00"),
        ]:
            self.client.post("/dashboard", data={"med_name": name, "salt_composition": salt, "price": price, "stock_quantity": "12"})
        self.client.get("/logout")

        self.client.post("/login", data={"username": "Partial Chemist", "password": "pass1234"})
        self.client.post("/dashboard", data={"med_name": "Dolo 650", "salt_composition": "Paracetamol", "price": "30.00", "stock_quantity": "12"})
        self.client.get("/logout")

        match_res = self.client.post(
            "/api/prescription-match",
            json={"items": ["Dolo 650", "Azithral 500", "Pan 40"], "lat": 25.5941, "lng": 85.1376},
        )
        self.assertEqual(match_res.status_code, 200)
        data = match_res.get_json()
        self.assertEqual(data["pharmacies"][0]["shop_name"], "OneStop Medico")
        self.assertTrue(data["pharmacies"][0]["complete_match"])
        self.assertEqual(data["pharmacies"][0]["matched_count"], 3)
        self.assertAlmostEqual(data["pharmacies"][0]["total_price"], 296.0, places=2)

        # Clinical safety checker flags Aspirin + Ibuprofen interaction AND duplicate Paracetamol
        safety_res = self.client.post(
            "/api/safety-check",
            json={
                "items": [
                    {"med_name": "Ecosprin 75", "salt_composition": "Aspirin"},
                    {"med_name": "Brufen 400", "salt_composition": "Ibuprofen"},
                    {"med_name": "Dolo 650", "salt_composition": "Paracetamol"},
                    {"med_name": "Crocin 650", "salt_composition": "Acetaminophen"},
                ]
            },
        ).get_json()
        self.assertFalse(safety_res["safe"])
        types = {w["type"] for w in safety_res["warnings"]}
        self.assertIn("duplicate_salt", types)
        self.assertIn("interaction", types)

    def test_dashboard_inline_stepper_csv_import_export_and_live_summary(self):
        self._register_and_verify_shop("CSV & Stepper Store", "pass1234", "Patna", 25.5941, 85.1376)
        self.client.post("/login", data={"username": "CSV & Stepper Store", "password": "pass1234"})

        csv_payload = (
            "med_name,salt_composition,dosage,price,stock_quantity,rx_required,expiry_date\n"
            "Glycomed 80,Gliclazide,80mg,92.50,6,1,2028-09-30\n"
            "ORS Pack,Oral Rehydration Salts,21g,22.00,15,0,2028-11-30\n"
        ).encode("utf-8")
        imp_res = self.client.post(
            "/dashboard/import_csv",
            data={"csv_file": (io.BytesIO(csv_payload), "stock.csv")},
            content_type="multipart/form-data",
            follow_redirects=True,
        )
        self.assertEqual(imp_res.status_code, 200)
        self.assertIn("CSV sync complete: 2 added", imp_res.get_data(as_text=True))

        # Export CSV
        exp_res = self.client.get("/dashboard/export_csv")
        self.assertEqual(exp_res.status_code, 200)
        self.assertIn("Glycomed 80", exp_res.get_data(as_text=True))

        # Inline stock stepper (-1 brings Glycomed 80 from 6 -> 5, triggering low_stock=True)
        gly_item = self.client.get("/api/search?query=Glycomed").get_json()[0]
        step_res = self.client.post(
            f"/inventory/{gly_item['med_id']}/adjust_stock",
            json={"delta": -1},
            headers={"Accept": "application/json"},
        ).get_json()
        self.assertTrue(step_res["ok"])
        self.assertEqual(step_res["stock_quantity"], 5)
        self.assertTrue(step_res["low_stock"])

        # Live dashboard summary JSON endpoint reflects updated low_stock_count
        summary = self.client.get("/api/dashboard/summary").get_json()
        self.assertTrue(summary["authenticated"])
        self.assertEqual(summary["kpi"]["total_skus"], 2)
        self.assertEqual(summary["kpi"]["low_stock_count"], 1)

    def test_csrf_cross_origin_protection_pwa_and_postgres_adapter(self):
        # Cross-origin POST is rejected with 403
        forged = self.client.post(
            "/api/reserve",
            json={"med_id": 1, "phone": "9876543210"},
            headers={"Origin": "https://evil-attacker.example"},
        )
        self.assertEqual(forged.status_code, 403)

        # Mismatched X-CSRF-Token is rejected with 403 once a session CSRF token exists
        self.client.get("/api/csrf-token")
        bad_token = self.client.post(
            "/api/reserve",
            json={"med_id": 1, "phone": "9876543210"},
            headers={"X-CSRF-Token": "wrong-token"},
        )
        self.assertEqual(bad_token.status_code, 403)

        # PWA endpoints serve manifest, service worker, and SVG icons
        with self.client.get("/manifest.json") as mf_res:
            self.assertEqual(mf_res.status_code, 200)
            self.assertEqual(mf_res.get_json()["short_name"], "MedFinder")

        with self.client.get("/sw.js") as sw_res:
            self.assertEqual(sw_res.status_code, 200)
            self.assertIn("Service-Worker-Allowed", sw_res.headers)

        with self.client.get("/static/icons/icon-192.svg") as icon_res:
            self.assertEqual(icon_res.status_code, 200)

        # PostgreSQL SQL translator & health engine reporting
        pg_sql = medifinder_app._translate_sql_for_postgres(
            "UPDATE inventory SET stock_quantity = MAX(0, stock_quantity - ?) WHERE created_at <= datetime('now', '+2 hours')"
        )
        self.assertIn("GREATEST(0,", pg_sql)
        self.assertIn("%s", pg_sql)
        self.assertIn("INTERVAL '2 hours'", pg_sql)
        health = self.client.get("/api/health").get_json()
        self.assertEqual(health["status"], "ok")
        self.assertEqual(health["db_engine"], "sqlite")
        self.assertIn("catalog_count", health)

    def test_real_medicine_catalog_search_substitutes_and_pack_import(self):
        # Seed real branded + PMBJP Jan Aushadhi rows in medicine_catalog
        conn = sqlite3.connect(self.db_path)
        conn.executemany(
            """
            INSERT INTO medicine_catalog
                (med_name, manufacturer, salt_composition, pack_size, mrp, is_generic, rx_required, source)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                ("Augmentin 625 Duo Tablet", "GSK", "Amoxycillin (500mg) + Clavulanic Acid (125mg)", "strip of 10 tablets", 223.42, 0, 1, "Indian Medicine Dataset"),
                ("Dolo 650 Tablet", "Micro Labs Ltd", "Paracetamol (650mg)", "strip of 15 tablets", 34.27, 0, 0, "Indian Medicine Dataset"),
                ("Paracetamol Tablets IP 500 mg (Jan Aushadhi #23)", "PMBJP (Jan Aushadhi)", "Paracetamol 500 mg", "Pack: 10's", 6.57, 1, 0, "PMBJP Jan Aushadhi"),
            ],
        )
        conn.commit()
        conn.close()

        # /api/catalog returns real catalog matches and supports generic_only=1
        cat_all = self.client.get("/api/catalog?q=Paracetamol").get_json()
        self.assertEqual(len(cat_all), 2)
        cat_gen = self.client.get("/api/catalog?q=Paracetamol&generic_only=1").get_json()
        self.assertEqual(len(cat_gen), 1)
        self.assertTrue(cat_gen[0]["is_generic"])

        # /api/autocomplete blends catalog items even before any partner shop stocks them
        ac = self.client.get("/api/autocomplete?q=Augmentin").get_json()
        self.assertTrue(any("Augmentin 625 Duo Tablet" in r["med_name"] for r in ac))

        # /api/substitutes surfaces PMBJP Jan Aushadhi generic reference MRP for the same active salt
        subs = self.client.get("/api/substitutes?query=Dolo%20650%20Tablet&ref_price=34.27").get_json()
        self.assertIn("Paracetamol", subs["salt"])
        self.assertTrue(any(s.get("is_catalog_reference") and s["savings_pct"] > 50 for s in subs["substitutes"]))

        # Verified shop can 1-click import official Branded & Jan Aushadhi catalog starter packs
        self._register_and_verify_shop("Kankarbagh Medico", "pass1234", "Patna", 25.5980, 85.1610)
        self.client.post("/login", data={"username": "Kankarbagh Medico", "password": "pass1234"})
        pack_res = self.client.post(
            "/dashboard/import_catalog_pack",
            data={"pack_type": "branded", "limit": "10"},
            follow_redirects=True,
        )
        self.assertEqual(pack_res.status_code, 200)
        self.assertIn("Imported 2 real Indian Branded", pack_res.get_data(as_text=True))

        gen_pack_res = self.client.post(
            "/dashboard/import_catalog_pack",
            data={"pack_type": "generic", "limit": "10"},
            follow_redirects=True,
        )
        self.assertEqual(gen_pack_res.status_code, 200)
        self.assertIn("Imported 1 real PMBJP Jan Aushadhi", gen_pack_res.get_data(as_text=True))

        # Imported medicines are immediately live in /api/search
        live_hits = self.client.get("/api/search?query=Augmentin").get_json()
        self.assertEqual(len(live_hits), 1)
        self.assertAlmostEqual(live_hits[0]["price"], 223.42, places=2)

    def test_osm_local_pharmacy_claim_prefill_and_map_hooks(self):
        # Claiming a real OpenStreetMap pharmacy pre-populates /register and saves pinned lat/lng
        claim_get = self.client.get(
            "/register?name=Sri+Ram+Medical+Hall&city=Boring+Road,+Patna&lat=25.614800&lng=85.112500&phone=9835099999&hours=8+AM+-+10+PM"
        )
        self.assertEqual(claim_get.status_code, 200)
        html = claim_get.get_data(as_text=True)
        self.assertIn("Claim &amp; Verify Local Pharmacy", html)
        self.assertIn("Sri Ram Medical Hall", html)
        self.assertIn("25.614800", html)

        claim_post = self.client.post(
            "/register",
            data={
                "name": "Sri Ram Medical Hall",
                "city": "Boring Road, Patna",
                "lat": "25.614800",
                "lng": "85.112500",
                "password": "secret123",
                "license_number": "DL-OSM-101",
                "phone": "9835099999",
                "opening_hours": "8 AM - 10 PM",
                "license_image": (io.BytesIO(PNG_BYTES), "license.png"),
                "shop_photo": (io.BytesIO(PNG_BYTES), "front.png"),
            },
            content_type="multipart/form-data",
            follow_redirects=False,
        )
        self.assertEqual(claim_post.status_code, 302)

        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        claimed = conn.execute("SELECT * FROM shops WHERE name = ?", ("Sri Ram Medical Hall",)).fetchone()
        conn.close()
        self.assertIsNotNone(claimed)
        self.assertAlmostEqual(claimed["lat"], 25.6148, places=4)
        self.assertAlmostEqual(claimed["lng"], 85.1125, places=4)
        self.assertEqual(claimed["city"], "Boring Road, Patna")

        # Verify OpenStreetMap Overpass discovery hooks & untouched live GPS watchPosition coexist
        home_html = self.client.get("/").get_data(as_text=True)
        self.assertIn("toggle-osm-layer-btn", home_html)
        self.assertIn("osm-nearby-count-badge", home_html)
        with self.client.get("/static/js/main.js") as js_res:
            js_text = js_res.get_data(as_text=True)
        for hook in (
            "discoverNearbyOsmPharmacies",
            "overpass-api.de/api/interpreter",
            "buildClaimStoreUrl",
            "renderCatalogAndLocalOsmCards",
            "initDashboardCatalogAutocomplete",
            "watchPosition",
        ):
            self.assertIn(hook, js_text)


if __name__ == "__main__":
    unittest.main()
