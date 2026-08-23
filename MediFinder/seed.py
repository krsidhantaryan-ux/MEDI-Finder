"""
MediFinder — Demo data seeding.
Idempotent: only inserts when the database is empty, so the app is usable
out of the box with realistic pharmacies, inventory, and a demo customer.
"""
import sqlite3
from werkzeug.security import generate_password_hash
from database import CATEGORIES


DEMO_SHOPS = [
    {
        "name": "Apollo Pharmacy — Frazer Road",
        "email": "apollo@medifinder.demo",
        "phone": "+91 98000 11111",
        "owner_name": "Rajeev Mehta",
        "license_number": "DL-PT-20-BRD-00451",
        "city": "Patna", "state": "Bihar", "pincode": "800001",
        "address": "Shop 12, Frazer Road, Near Dak Bungalow",
        "lat": 25.6110, "lng": 85.1430,
        "open_time": "08:00", "close_time": "23:00", "delivery": 1,
        "description": "24/7 chain pharmacy with full prescription, surgical, and wellness range.",
        "inventory": [
            ("Dolo 650", "Paracetamol", "Tablets & Capsules", "Micro Labs", "650mg, 15 tablets", 32.00, 30.50, 120, 0),
            ("Azithral 500", "Azithromycin", "Tablets & Capsules", "Alembic", "500mg, 5 tablets", 119.00, 95.00, 40, 1),
            ("Augmentin 625 Duo", "Amoxicillin+Clavulanic Acid", "Tablets & Capsules", "GSK", "625mg, 10 tablets", 410.00, 356.00, 18, 1),
            ("Crocin Advance", "Paracetamol", "Tablets & Capsules", "GSK", "500mg, 15 tablets", 30.00, 27.50, 200, 0),
            ("Glycomet 500", "Metformin", "Diabetes Care", "USV", "500mg, 20 tablets", 86.00, 74.00, 55, 1),
            ("Telma 40", "Telmisartan", "Cardiac", "Glenmark", "40mg, 15 tablets", 145.00, 121.00, 33, 1),
            ("Ascoril LS", "Ambroxol+Levosalbutamol", "Cough & Cold", "Glenmark", "100ml syrup", 135.00, 118.00, 26, 0),
            ("Volini Gel", "Diclofenac", "Topicals & Creams", "Sun Pharma", "30g tube", 115.00, 99.00, 64, 0),
            ("Becosules Z", "B-Complex+Vitamin C", "Vitamins & Supplements", "Pfizer", "20 capsules", 38.00, 33.00, 300, 0),
            ("Glucometer Strips", "Blood Glucose Test Strips", "Medical Devices", "Accu-Chek", "Pack of 50", 1190.00, 999.00, 12, 0),
        ],
    },
    {
        "name": "Wellness Forever Chemist",
        "email": "wellness@medifinder.demo",
        "phone": "+91 98000 22222",
        "owner_name": "Priya Singh",
        "license_number": "DL-PT-20-BRD-00782",
        "city": "Patna", "state": "Bihar", "pincode": "800014",
        "address": "Ground Floor, Boring Road, Srikrishnapuri",
        "lat": 25.6148, "lng": 85.1125,
        "open_time": "09:00", "close_time": "22:30", "delivery": 1,
        "description": "Neighbourhood chemist with free same-day delivery within 5 km.",
        "inventory": [
            ("Paracetamol 500", "Paracetamol", "Tablets & Capsules", "Cipla", "500mg, 10 tablets", 22.00, 18.50, 500, 0),
            ("Dolo 650", "Paracetamol", "Tablets & Capsules", "Micro Labs", "650mg, 15 tablets", 32.00, 28.00, 80, 0),
            ("Cetzine 10", "Cetirizine", "Cough & Cold", "Cipla", "10mg, 10 tablets", 28.00, 22.00, 240, 0),
            ("Pantop-D", "Pantoprazole+Domperidone", "Tablets & Capsules", "Alkem", "10 capsules", 95.00, 79.00, 70, 1),
            ("Zincovit", "Multivitamin+Zinc", "Vitamins & Supplements", "Apex", "15 tablets", 98.00, 85.00, 150, 0),
            ("Dabur Chyawanprash", "Ayurvedic Immunity", "Ayurvedic & Herbal", "Dabur", "1kg jar", 410.00, 365.00, 24, 0),
            ("Moov Cream", "Diclofenac+Menthol", "Topicals & Creams", "Reckitt", "50g", 175.00, 149.00, 40, 0),
            ("Cough Syrup Benadryl", "Diphenhydramine", "Cough & Cold", "Johnson & Johnson", "150ml", 165.00, 139.00, 28, 0),
        ],
    },
    {
        "name": "City Medico — Kankarbagh",
        "email": "citymedico@medifinder.demo",
        "phone": "+91 98000 33333",
        "owner_name": "Anil Kumar",
        "license_number": "DL-PT-20-BRD-01109",
        "city": "Patna", "state": "Bihar", "pincode": "800020",
        "address": "Main Road Kankarbagh, Opposite Hanuman Mandir",
        "lat": 25.5980, "lng": 85.1580,
        "open_time": "07:30", "close_time": "22:00", "delivery": 0,
        "description": "Family-run chemist established 1996. Generics a speciality.",
        "inventory": [
            ("Metformin 500 SR", "Metformin", "Diabetes Care", "Generic", "500mg, 20 tablets", 48.00, 39.00, 110, 1),
            ("Amlodipine 5", "Amlodipine", "Cardiac", "Generic", "5mg, 10 tablets", 42.00, 33.00, 90, 1),
            ("Atorvastatin 10", "Atorvastatin", "Cardiac", "Generic", "10mg, 15 tablets", 96.00, 78.00, 60, 1),
            ("Dolo 650", "Paracetamol", "Tablets & Capsules", "Micro Labs", "650mg, 15 tablets", 32.00, 26.00, 150, 0),
            ("ORS Sachet", "Electrolytes", "Syrups & Liquids", "Electral", "21.8g, 4 sachets", 24.00, 20.00, 400, 0),
            ("Digene Gel", "Antacid", "Syrups & Liquids", "Abbott", "200ml", 125.00, 109.00, 35, 0),
            ("Betadine Ointment", "Povidone-Iodine", "Topicals & Creams", "Win-Medicure", "15g tube", 75.00, 65.00, 48, 0),
            ("Insulin Pen Needles", "Pen Needles 32G", "Medical Devices", "BD", "Pack of 100", 750.00, 675.00, 15, 0),
        ],
    },
    {
        "name": "24x7 MedHub — Bailey Road",
        "email": "medhub@medifinder.demo",
        "phone": "+91 98000 44444",
        "owner_name": "Sneha Verma",
        "license_number": "DL-PT-20-BRD-02244",
        "city": "Patna", "state": "Bihar", "pincode": "800014",
        "address": "Jagdeo Path, Bailey Road, Near Raja Bazar",
        "lat": 25.6105, "lng": 85.0920,
        "is_open_24h": 1, "delivery": 1,
        "description": "Round-the-clock emergency pharmacy. Surgical and baby care section.",
        "inventory": [
            ("Dolo 650", "Paracetamol", "Tablets & Capsules", "Micro Labs", "650mg, 15 tablets", 32.00, 30.00, 220, 0),
            ("I-Pill", "Levonorgestrel", "Baby & Maternity", "Cipla", "1 tablet", 110.00, 99.00, 40, 0),
            ("Thermometer Digital", "Digital Thermometer", "Medical Devices", "Omron", "MC-246", 225.00, 199.00, 30, 0),
            ("Pulse Oximeter", "SpO2 Monitor", "Medical Devices", "Dr. Morepen", "PO-12A", 1499.00, 1249.00, 18, 0),
            ("N95 Mask", "Respirator Mask", "Personal Care", "3M", "Pack of 5", 250.00, 199.00, 500, 0),
            ("Sanitizer 500ml", "Alcohol-based Hand Rub", "Personal Care", "Dettol", "500ml pump", 180.00, 149.00, 120, 0),
            ("Simyl MCT Oil", "MCT+LCT Supplement", "Baby & Maternity", "FDC", "100ml", 320.00, 279.00, 22, 0),
            ("Glucometer Strips", "Blood Glucose Test Strips", "Medical Devices", "OneTouch", "Pack of 50", 999.00, 849.00, 25, 0),
            ("Azithral 500", "Azithromycin", "Tablets & Capsules", "Alembic", "500mg, 5 tablets", 119.00, 105.00, 50, 1),
        ],
    },
    {
        "name": "Sanjeevani Ayurveda & Generic",
        "email": "sanjeevani@medifinder.demo",
        "phone": "+91 98000 55555",
        "owner_name": "Dr. Vikas Anand",
        "license_number": "DL-PT-20-BRD-03120",
        "city": "Patna", "state": "Bihar", "pincode": "800006",
        "address": "Ashok Rajpath, Opposite PMCH",
        "lat": 25.6220, "lng": 85.1520,
        "open_time": "09:00", "close_time": "21:00", "delivery": 0,
        "description": "Ayurvedic, herbal and Jan Aushadhi generic medicines at honest prices.",
        "inventory": [
            ("Ashwagandha 60 tabs", "Withania Somnifera", "Ayurvedic & Herbal", "Himalaya", "60 tablets", 220.00, 185.00, 80, 0),
            ("Tulsi Drops", "Ocimum Sanctum", "Ayurvedic & Herbal", "Patanjali", "30ml", 195.00, 165.00, 90, 0),
            ("Dolo 650", "Paracetamol", "Tablets & Capsules", "Micro Labs", "650mg, 15 tablets", 32.00, 24.00, 130, 0),
            ("Paracetamol 500", "Paracetamol", "Tablets & Capsules", "Jan Aushadhi", "500mg, 10 tablets", 12.00, 8.00, 600, 0),
            ("Cetzine 10", "Cetirizine", "Cough & Cold", "Jan Aushadhi", "10mg, 10 tablets", 18.00, 12.00, 200, 0),
            ("Chyawanprash 1kg", "Ayurvedic Immunity", "Ayurvedic & Herbal", "Patanjali", "1kg", 345.00, 299.00, 45, 0),
            ("Liv.52 Tablets", "Liver Care", "Ayurvedic & Herbal", "Himalaya", "100 tablets", 145.00, 125.00, 70, 0),
        ],
    },
]


REVIEWS = [
    # (shop_index, name, rating, comment)
    (0, "Rahul Sharma", 5, "Found a rare cardiac med here within minutes. Great staff."),
    (0, "Ananya Roy", 4, "Well stocked. Slightly crowded during evenings."),
    (1, "Kavya Nair", 5, "Free delivery to my door in 30 minutes. Lifesaver!"),
    (2, "Mohit Gupta", 4, "Best generic prices in Kankarbagh. Honest chemist."),
    (3, "Sneha R.", 5, "Open at 3am when my son had fever. Thank you MedHub."),
    (3, "Arjun P.", 4, "Good surgical supplies, helpful pharmacist."),
    (4, "Dr. Shreya", 5, "Excellent Ayurvedic section and genuine generic prices."),
]


def seed_demo_data(db_path):
    """Populate empty database with demo shops, inventory, reviews, and a demo customer."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON;")
    try:
        existing = conn.execute("SELECT COUNT(*) FROM shops").fetchone()[0]
        if existing:
            conn.close()
            return False

        cat_name_to_id = {}
        for name, slug, icon in CATEGORIES:
            conn.execute(
                "INSERT OR IGNORE INTO categories (name, slug, icon) VALUES (?, ?, ?)",
                (name, slug, icon),
            )
            row = conn.execute("SELECT id FROM categories WHERE name=?", (name,)).fetchone()
            if row:
                cat_name_to_id[name] = row[0]

        shop_ids = []
        for shop in DEMO_SHOPS:
            cur = conn.execute(
                """
                INSERT INTO shops
                (name, email, phone, owner_name, password_hash, license_number, shop_photo,
                 description, address, city, state, pincode, lat, lng,
                 open_time, close_time, is_open_24h, delivery, status)
                VALUES (?, ?, ?, ?, ?, ?, NULL, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'Verified')
                """,
                (shop["name"], shop["email"], shop["phone"], shop["owner_name"],
                 generate_password_hash("demo1234"), shop["license_number"],
                 shop["description"], shop["address"],
                 shop["city"], shop["state"], shop["pincode"], shop["lat"],
                 shop["lng"], shop.get("open_time", "09:00"),
                 shop.get("close_time", "21:00"), shop.get("is_open_24h", 0),
                 shop.get("delivery", 0)),
            )
            sid = cur.lastrowid
            shop_ids.append(sid)
            for (med, salt, cat, mfr, dosage, mrp, price, qty, rx) in shop["inventory"]:
                conn.execute(
                    """
                    INSERT INTO inventory
                    (shop_id, med_name, salt_composition, category_id, manufacturer,
                     dosage, mrp, price, stock_quantity, prescription, is_active)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1)
                    """,
                    (sid, med, salt, cat_name_to_id.get(cat), mfr, dosage,
                     mrp, price, qty, rx),
                )

        for (si, name, rating, comment) in REVIEWS:
            if si < len(shop_ids):
                conn.execute(
                    "INSERT INTO reviews (shop_id, customer_name, rating, comment) VALUES (?, ?, ?, ?)",
                    (shop_ids[si], name, rating, comment),
                )

        # Demo customer — email demo@medifinder.app / password demo1234
        conn.execute(
            """
            INSERT INTO customers (name, email, phone, password_hash, city)
            VALUES (?, ?, ?, ?, ?)
            """,
            ("Demo Patient", "demo@medifinder.app", "+91 90000 00000",
             generate_password_hash("demo1234"), "Patna"),
        )

        conn.commit()
        return True
    finally:
        conn.close()
