# MediFinder

A complete medicine-availability platform. Patients search by brand or active
ingredient across **verified nearby pharmacies**, see live stock / pricing /
distance on a map, and place a 2-hour hold. Pharmacists manage inventory,
reservations and store profile; an admin console verifies pharmacies and
monitors the network.

![Stack](https://img.shields.io/badge/Flask-3-000?logo=flask)
![DB](https://img.shields.io/badge/SQLite-3-003b57?logo=sqlite)
![Leaflet](https://img.shields.io/badge/Maps-Leaflet-199900?logo=leaflet)

---

## Quick start

```bash
cd MediFinder
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python app.py
```

Open <http://localhost:5000>.

The database (`medifinder.db`) is created automatically on first run and
seeded with **5 verified pharmacies**, 42 medicines across 11 categories,
realistic reviews and a demo customer.

### Demo credentials

| Role       | Login                              | Password     |
|------------|------------------------------------|--------------|
| Customer   | `demo@medifinder.app`              | `demo1234`   |
| Pharmacy   | any seeded shop name (e.g. `Apollo Pharmacy — Frazer Road`) | `demo1234` |
| Admin      | `admin`                            | `admin123`   |

Set `ADMIN_USER`, `ADMIN_PASS` and `SECRET_KEY` environment variables in
production.

---

## Features

### For patients
- **Search by brand or salt composition** (case-insensitive, fuzzy)
- **Live map** (Leaflet + CARTO tiles) with distance-based sorting via Haversine
- **Browser geolocation** with one-tap "use my location" and reverse geocoding
- **Filters**: category, in-stock only, Rx / OTC, sort by distance / price / stock
- **Medicine autocomplete** and trending searches on the landing page
- **2-hour holds** with phone, name, quantity and note — no payment, no friction
- **Customer accounts** (email + hashed password):
  - reservation history with cancel action
  - favourite medicines for one-tap re-search
  - star reviews on pharmacies
- **Pharmacy profile pages** with inventory filter, hours, phone, directions,
  delivery / 24-hour badges and community reviews
- **Dark mode** (system preference + toggle, persisted)
- Fully responsive, PWA-friendly meta

### For pharmacies (`/pharmacy`)
- Registration with drug-license, shop photo and GST upload (admin-verified)
- **Dashboard** with KPIs: items in stock, stock value, reservations, expiring
- Full **inventory management**:
  - add with category, manufacturer, batch, expiry, MRP, price, stock, Rx flag
  - inline stock quick-update
  - edit / delete items
  - low-stock / out-of-stock indicators
- **Reservation workflow**: Pending → Confirmed → Collected (auto-decrements
  stock) or Cancelled. Holds expire automatically after 2 hours.
- **Store profile**: hours (incl. 24-hour toggle), delivery toggle, description,
  photo, contact details
- **Location pinning** via draggable map marker, address search (Nominatim) or
  "use my location" — feeds straight into the customer distance sort
- Pending-verification banner; inventory can be prepared while under review

### For admins (`/admin`)
- Network stats (shops, verified, pending, customers, inventory, reservations, reviews)
- **Verify / reject / suspend / reinstate / delete** pharmacies, with rejection reason
- Document viewer (license, shop photo, GST)
- Verified pharmacy table with quick links to public profiles
- Live **recent reservations** feed
- **Audit log** of all admin and user actions

### Engineering
- Single-file Flask app plus `database.py` (schema + idempotent migrations)
  and `seed.py` (demo data)
- Passwords hashed with Werkzeug (PBKDF2); no plaintext
- All mutating admin/shop actions use POST; destructive actions confirm
- SQLite with foreign keys, indexes on all hot query paths
- JSON APIs for search, autocomplete, nearby shops, reservations, favourites,
  reviews and inventory updates
- Custom design system — editorial "Apothecary Modern" aesthetic with Fraunces
  display serif + Inter body, warm paper background, teal/amber palette.
  No Bootstrap, no glassmorphism, no purple-blue gradients.

---

## Project structure

```
MediFinder/
├── app.py              # Flask app, routes, APIs
├── database.py         # Schema, migrations, connection helpers
├── seed.py             # Idempotent demo data
├── requirements.txt
├── medifinder.db       # Auto-created SQLite DB
├── static/
│   ├── css/style.css   # Full custom design system
│   ├── js/app.js       # Theme, toasts, map, reservation modal, favourites
│   ├── img/favicon.svg
│   └── uploads/        # Pharmacy documents / photos
└── templates/
    ├── base.html
    ├── index.html              # Landing + search hero
    ├── search.html             # Results + map
    ├── shop_profile.html
    ├── customer_auth.html      # Combined login/register
    ├── account.html
    ├── shop_login.html
    ├── shop_register.html
    ├── shop_dashboard.html
    ├── admin_login.html
    ├── admin_dashboard.html
    └── error.html
```

## API summary

| Method | Path                              | Description                          |
|--------|-----------------------------------|--------------------------------------|
| GET    | `/api/search?q=&city=&cat=&lat=&lng=&sort=&in_stock=&rx=` | Search inventory     |
| GET    | `/api/autocomplete?q=`            | Medicine name/salt suggestions       |
| GET    | `/api/shops/nearby?lat=&lng=`     | Closest verified pharmacies          |
| GET    | `/api/shop/<id>`                  | Shop + inventory JSON                |
| POST   | `/api/reserve`                    | Place a 2-hour hold                  |
| GET/POST/DELETE | `/api/favourites`        | Customer favourites (auth)           |
| POST   | `/api/shops/<id>/review`          | Star + comment (auth)                |
| POST   | `/pharmacy/inventory/<id>/update` | Update item JSON (shop auth)         |

---

## Notes

- The 2-hour hold is enforced by a `held_until` timestamp; expired holds are
  marked the next time a shop dashboard or account page is loaded.
- Map tiles © OpenStreetMap, © CARTO. Geocoding via Nominatim — please be
  polite with request volume.
- This is a reference implementation; put it behind a real WSGI server
  (gunicorn/uwsgi) and set strong `SECRET_KEY` / admin credentials before any
  production use.
