# MediFinder

MediFinder is a local healthcare utility for finding medicine at verified nearby pharmacies. Patients search by brand or active ingredient, compare live stock, price, strength, distance and opening status on a map, then place a 2-hour pickup hold. Pharmacies manage daily inventory and reservations; admins verify stores and review prescription upload requests.

![Stack](https://img.shields.io/badge/Flask-3-000?logo=flask)
![DB](https://img.shields.io/badge/SQLite-3-003b57?logo=sqlite)
![Maps](https://img.shields.io/badge/Maps-OpenStreetMap-7ebc6f?logo=openstreetmap)

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

Run the built-in smoke checks with:

```bash
python tests/smoke_app.py
```

The database (`medifinder.db`) is created automatically on first run and seeded with verified pharmacies, medicines, reviews and a demo customer.

### Demo credentials

| Role | Login | Password |
|---|---|---|
| Customer | `demo@medifinder.app` | `demo1234` |
| Pharmacy | any seeded shop name, e.g. `Apollo Pharmacy — Frazer Road` | `demo1234` |
| Admin | `admin` | `admin123` |

Set `ADMIN_USER`, `ADMIN_PASS` and `SECRET_KEY` environment variables in production.

---

## Product direction

The UI is intentionally restrained and practical: off-white healthcare surfaces, solid cards, clear comparison tables/cards, map-first local context and minimal motion for feedback. It avoids generic AI/SaaS landing-page tropes and focuses on the everyday workflows patients and pharmacies need.

---

## Features

### For patients
- **Search by brand, salt composition or manufacturer**.
- **Strength / dosage and quantity inputs** so results are closer to the exact medicine needed.
- **OpenStreetMap-powered maps** on the homepage, search results, pharmacy profiles and the standalone `/map` pharmacy explorer.
- **Auto-location** with backend reverse geocoding on the homepage, search page, pharmacy map, prescription upload and pharmacy profile tools.
- **Filters** for category, in-stock only, prescription / OTC and sorting by distance / price / stock.
- **Medicine autocomplete** and popular searches on the landing page.
- **2-hour pickup holds** with phone, name, quantity and note — no payment required.
- **Prescription upload** (`/prescription`) for image/PDF requests that need pharmacist review before matching stock.
- **Customer account** with active holds, saved medicines, prescription-request history and reviews.
- **Pharmacy profile pages** with inventory filter, hours, phone, directions, delivery / 24-hour badges and community reviews.
- **Dark mode** with persisted preference.

### For pharmacies (`/pharmacy`)
- Registration with drug-licence, shop photo and optional GST upload for admin verification.
- Operations dashboard with KPIs: in-stock items, stock value, reservation count and expiring items.
- **Low-stock and expiring-stock queues** for daily pharmacy work.
- Inventory management: add category, manufacturer, batch, expiry, MRP, selling price, stock, dosage and prescription flag.
- Inline stock quick-update, edit and delete actions.
- Reservation workflow: **Pending → Confirmed → Collected** (auto-decrements stock) or Cancelled. Holds expire automatically after 2 hours.
- Store profile management: hours, 24-hour toggle, delivery toggle, description, photo and contact details.
- Location pinning with draggable map marker, address search or “use my location”.

### For admins (`/admin`)
- Network stats for pharmacies, customers, inventory, reservations, prescription requests and reviews.
- Verify, reject, suspend, reinstate or delete pharmacies with rejection notes.
- Document viewer for licence, shop photo and GST uploads.
- **Prescription review queue** with Submitted / Reviewing / Matched / Closed actions.
- Recent reservations feed and audit log.

### Engineering
- Flask app with `database.py` schema/migrations and `seed.py` idempotent demo data.
- SQLite with foreign keys and indexes on hot query paths.
- Passwords hashed with Werkzeug PBKDF2.
- Mutating admin/shop actions use POST; destructive actions confirm in the UI.
- JSON APIs for search, autocomplete, nearby shops, public geocoding/reverse-geocoding, reservations, favourites, reviews and inventory updates.
- Motion for JavaScript is used sparingly for scroll reveal, button feedback, result-card entry, modal/toast feedback and reduced-motion-friendly interactions.

---

## Project structure

```text
MediFinder/
├── app.py              # Flask app, routes, APIs
├── database.py         # Schema, migrations, connection helpers
├── seed.py             # Idempotent demo data
├── requirements.txt
├── medifinder.db       # Auto-created SQLite DB
├── static/
│   ├── css/style.css   # Product UI system
│   ├── js/app.js       # Theme, toasts, maps, reservation modal, favourites
│   ├── js/motion-system.js
│   ├── img/favicon.svg
│   └── uploads/        # Pharmacy documents, photos and prescription uploads
└── templates/
    ├── base.html
    ├── index.html
    ├── search.html
    ├── map.html
    ├── prescription.html
    ├── shop_profile.html
    ├── customer_auth.html
    ├── account.html
    ├── shop_login.html
    ├── shop_register.html
    ├── shop_dashboard.html
    ├── admin_login.html
    ├── admin_dashboard.html
    └── error.html
```

## API summary

| Method | Path | Description |
|---|---|---|
| GET | `/map?city=` | Standalone verified pharmacy map |
| GET | `/api/search?q=&city=&cat=&lat=&lng=&sort=&dosage=&quantity=&in_stock=&rx=` | Search inventory |
| GET | `/api/autocomplete?q=` | Medicine name/salt suggestions |
| GET | `/api/shops/nearby?lat=&lng=` | Closest verified pharmacies |
| GET | `/api/geocode?q=` | Keyless public OpenStreetMap/Nominatim geocoding with local fallback |
| GET | `/api/reverse-geocode?lat=&lng=` | Keyless public OpenStreetMap/Nominatim reverse geocoding with local fallback |
| GET | `/api/location/estimate?city=` | Local approximate fallback when browser location is blocked |
| GET | `/api/shop/<id>` | Shop + inventory JSON |
| POST | `/api/reserve` | Place a 2-hour pickup hold |
| GET/POST/DELETE | `/api/favourites` | Customer favourites |
| POST | `/api/shops/<id>/review` | Pharmacy review |
| POST | `/pharmacy/inventory/<id>/update` | Update item JSON or form data |
| GET/POST | `/prescription` | Prescription upload request |

---

## Deployment

The repo is deployment-ready:
- `gunicorn` is in `requirements.txt`
- `Procfile` works for Railway/Heroku/Dokku-style hosts
- `render.yaml` supports Render deployment
- `DATABASE_PATH`, `UPLOAD_FOLDER` and `SECRET_KEY` can be set via env vars

### One-click deploy to Render

Open `render.com/deploy?repo=https://github.com/krsidhantaryan-ux/MEDI-Finder` and follow the prompts.

Settings from `render.yaml`:

| Setting | Value |
|---|---|
| Root directory | `MediFinder` |
| Build command | `pip install -r requirements.txt` |
| Start command | `gunicorn app:app --workers 1 --threads 4 --timeout 60 --bind 0.0.0.0:$PORT` |
| Health check | `/` |

After first deploy, change `ADMIN_PASS` in the host dashboard and redeploy.

**Free-tier caveat:** SQLite and uploaded files live on the ephemeral filesystem unless you attach persistent storage. For durable data, set `DATABASE_PATH` and `UPLOAD_FOLDER` to a mounted persistent disk.

### Environment variables

| Variable | Purpose | Default |
|---|---|---|
| `SECRET_KEY` | Flask session signing | dev-only key — set in production |
| `ADMIN_USER` | Admin login username | `admin` |
| `ADMIN_PASS` | Admin login password | `admin123` |
| `DATABASE_PATH` | Absolute path to SQLite file | `MediFinder/medifinder.db` |
| `UPLOAD_FOLDER` | Absolute path for uploads | `MediFinder/static/uploads` |
| `FLASK_ENV` | Set to `production` to force secure cookies | unset |
| `PORT` | Port to bind | `5000` |

## Notes

- The 2-hour hold is enforced by a `held_until` timestamp; expired holds are marked when shop dashboard or customer account pages load.
- Map tiles © OpenStreetMap, © CARTO. Geocoding via Nominatim; keep request volume polite.
- MediFinder is not medical advice and does not replace pharmacist or physician guidance.
- Before production use, run behind a real WSGI server and set strong secrets/admin credentials.
