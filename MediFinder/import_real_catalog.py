"""
Import real Indian Branded Medicines (junioralive/Indian-Medicine-Dataset, 253,973 rows)
and real PMBJP Jan Aushadhi Generic Medicines (2,308 rows) into MedFinder's `medicine_catalog`,
and stock verified partner stores with real catalog formulations.

Usage:
    .venv/bin/python MediFinder/import_real_catalog.py
"""

import collections
import csv
import os
import re
import sqlite3
import sys
import tarfile
import tempfile
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import app as medifinder_app  # noqa: E402

TARBALL_URL = "https://codeload.github.com/Dev027-ai/GENERIC_SAATHI/tar.gz/HEAD"

PRIORITY_ESSENTIAL_PREFIXES = (
    "augmentin 625",
    "azithral 500",
    "ascoril ls",
    "allegra 120",
    "avil 25",
    "amlokind 5",
    "atorva 10",
    "becosules",
    "brufen 400",
    "calpol 650",
    "cetzine",
    "chymoral forte",
    "ciplox 500",
    "combiflam",
    "crocin",
    "dolo 650",
    "digene",
    "ecosprin 75",
    "electral",
    "evion 400",
    "glycomet",
    "limcee",
    "meftal spas",
    "metrogyl 400",
    "montair lc",
    "neurobion forte",
    "okacet",
    "ondem",
    "omez",
    "pan 40",
    "pan d",
    "pantocid 40",
    "rantac 150",
    "rosuvas 10",
    "shelcal 500",
    "sinarest",
    "stamlo 5",
    "taxim o 200",
    "telma 40",
    "thyronorm 50",
    "udiliv 300",
    "vertin 16",
    "volini",
    "voveran",
    "zerodol",
    "zincovit",
)


def _clean_salt(c1, c2=""):
    parts = [re.sub(r"\s+", " ", (p or "").strip()) for p in (c1, c2) if (p or "").strip()]
    return " + ".join(parts)


def _extract_salt_from_generic_title(generic_name, strength=""):
    cleaned = re.sub(
        r"\b(Tablets?|Capsules?|Syrup|Injection|Suspension|Drops|Ointment|Cream|Gel|Powder|Solution|Inhaler|Respules|Sachet|IP|BP|USP)\b",
        "",
        generic_name or "",
        flags=re.IGNORECASE,
    )
    cleaned = re.sub(r"\band\b", "+", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" ,+-")
    if not cleaned and strength:
        return strength
    return cleaned


def ensure_raw_csvs(cache_dir="/tmp/real_med_data"):
    branded_csv = os.path.join(cache_dir, "data", "input", "indian_medicine_data.csv")
    jana_csv = os.path.join(cache_dir, "data", "input", "jan_aushadhi_extracted(3).csv")
    if os.path.isfile(branded_csv) and os.path.isfile(jana_csv):
        return branded_csv, jana_csv

    os.makedirs(cache_dir, exist_ok=True)
    with tempfile.NamedTemporaryFile(suffix=".tar.gz", delete=False) as tmp:
        tmp_path = tmp.name
    try:
        req = urllib.request.Request(TARBALL_URL, headers={"User-Agent": "MedFinder-Catalog-Importer"})
        with urllib.request.urlopen(req, timeout=60) as resp, open(tmp_path, "wb") as out:
            out.write(resp.read())
        with tarfile.open(tmp_path, "r:gz") as tar:
            for member in tar.getmembers():
                parts = member.name.split("/", 1)
                if len(parts) == 2 and parts[1].startswith("data/input/"):
                    member.name = parts[1]
                    tar.extract(member, cache_dir)
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)
    return branded_csv, jana_csv


def load_real_catalog_records(branded_csv, jana_csv, per_letter_cap=360):
    catalog_rows = []
    seen_names = set()

    # 1. Load ALL valid real PMBJP Jan Aushadhi Generic medicines (~2,280 records)
    jana_essentials = []
    with open(jana_csv, encoding="utf-8-sig", errors="replace") as f:
        reader = csv.DictReader(f)
        for row in reader:
            gname = re.sub(r"\s+", " ", (row.get("generic_name") or "").strip())
            if not gname:
                continue
            try:
                price = round(float(row.get("price_inr") or 0.0), 2)
            except ValueError:
                continue
            if price <= 0:
                continue
            unit_raw = (row.get("unit_size_raw") or "").strip()
            strength = (row.get("strength") or "").strip()
            drug_code = (row.get("drug_code") or "").strip()
            pack_label = f"Pack: {unit_raw}" if unit_raw else strength
            salt = _extract_salt_from_generic_title(gname, strength)
            rx_flag = 1 if medifinder_app.infer_rx_required(gname, salt, 0) else 0
            display_name = f"{gname} (Jan Aushadhi #{drug_code})" if drug_code else f"{gname} (Jan Aushadhi)"
            key = display_name.lower()
            if key in seen_names:
                continue
            seen_names.add(key)
            rec = (
                display_name,
                "PMBJP (Jan Aushadhi)",
                salt,
                pack_label,
                price,
                1,
                rx_flag,
                "PMBJP Jan Aushadhi",
            )
            catalog_rows.append(rec)
            if any(tok in salt.lower() for tok in ("paracetamol", "azithromycin", "amoxycillin", "amoxicillin", "pantoprazole", "metformin", "telmisartan", "atorvastatin", "cetirizine", "aceclofenac", "aspirin", "ibuprofen", "montelukast", "amlodipine", "ciprofloxacin", "ondansetron")):
                if len(jana_essentials) < 28:
                    jana_essentials.append(rec)

    # 2. Load stratified top real Indian Branded medicines across A-Z (~9,500+ records)
    priority_branded = []
    regular_branded = []
    letter_counts = collections.Counter()

    with open(branded_csv, encoding="utf-8-sig", errors="replace") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if (row.get("Is_discontinued") or "").strip().upper() == "TRUE":
                continue
            name = re.sub(r"\s+", " ", (row.get("name") or "").strip())
            if not name or name.lower() in seen_names:
                continue
            try:
                price = round(float(row.get("price(₹)") or 0.0), 2)
            except ValueError:
                continue
            if price <= 0:
                continue

            salt = _clean_salt(row.get("short_composition1"), row.get("short_composition2"))
            if not salt:
                continue
            mfr = re.sub(r"\s+", " ", (row.get("manufacturer_name") or "").strip())
            pack = re.sub(r"\s+", " ", (row.get("pack_size_label") or "").strip())
            rx_flag = 1 if medifinder_app.infer_rx_required(name, salt, 0) else 0

            first_ch = name[0].upper()
            is_priority = name.lower().startswith(PRIORITY_ESSENTIAL_PREFIXES)
            if not is_priority and letter_counts[first_ch] >= per_letter_cap:
                continue

            seen_names.add(name.lower())
            letter_counts[first_ch] += 1
            rec = (
                name,
                mfr,
                salt,
                pack,
                price,
                0,
                rx_flag,
                "Indian Medicine Dataset",
            )
            if is_priority and len(priority_branded) < 120:
                priority_branded.append(rec)
            else:
                regular_branded.append(rec)

    # Put priority prescribed Indian brands first so 1-click starter packs grab India's top staples
    ordered_catalog = priority_branded + catalog_rows + regular_branded
    return ordered_catalog, priority_branded, jana_essentials


def import_into_sqlite(db_path=None):
    target_db = db_path or medifinder_app.DEFAULT_DB_PATH
    medifinder_app.app.config["DATABASE"] = target_db
    medifinder_app.init_db()

    branded_csv, jana_csv = ensure_raw_csvs()
    ordered_catalog, priority_branded, jana_essentials = load_real_catalog_records(branded_csv, jana_csv)

    with sqlite3.connect(target_db) as conn:
        conn.row_factory = sqlite3.Row
        conn.execute("DELETE FROM medicine_catalog")
        conn.executemany(
            """
            INSERT INTO medicine_catalog (
                med_name, manufacturer, salt_composition, pack_size, mrp, is_generic, rx_required, source
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            ordered_catalog,
        )

        # Enrich existing verified Patna shops with real formulations from these real datasets
        # (never deleting or altering existing rows, keeping all prices > 0)
        shop_stock_plan = {
            1: priority_branded[:22],       # Apollo (Danapur, Patna)
            18: priority_branded[8:30],     # Apollo (Bailey Road, Patna)
            14: priority_branded[15:35],    # Allentra (Patna)
            17: priority_branded[:14],      # arnav (Patna)
            15: jana_essentials[:24],       # Janaushadhi (Kankarbagh, Patna — official PMBJP generics!)
        }
        added_inv = 0
        for shop_id, med_list in shop_stock_plan.items():
            shop_exists = conn.execute(
                "SELECT id FROM shops WHERE id = ? AND status = 'Verified'",
                (shop_id,),
            ).fetchone()
            if not shop_exists:
                continue
            for idx, (mname, _mfr, msalt, mpack, mmrp, _is_gen, mrx, _src) in enumerate(med_list):
                dup = conn.execute(
                    "SELECT id FROM inventory WHERE shop_id = ? AND LOWER(med_name) = LOWER(?)",
                    (shop_id, mname),
                ).fetchone()
                if dup:
                    continue
                stock_qty = 6 + ((shop_id * 7 + idx * 5) % 28)
                conn.execute(
                    """
                    INSERT INTO inventory (
                        shop_id, med_name, salt_composition, price, stock_quantity, dosage, rx_required, expiry_date
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, '2028-12-31')
                    """,
                    (shop_id, mname, msalt, mmrp, stock_qty, mpack, mrx),
                )
                added_inv += 1

        conn.execute("ANALYZE")
        conn.commit()
        cat_total = conn.execute("SELECT COUNT(*) FROM medicine_catalog").fetchone()[0]
        gen_total = conn.execute("SELECT COUNT(*) FROM medicine_catalog WHERE is_generic = 1").fetchone()[0]
        inv_total = conn.execute("SELECT COUNT(*) FROM inventory").fetchone()[0]

    return {
        "catalog_total": cat_total,
        "janaushadhi_generics": gen_total,
        "branded_medicines": cat_total - gen_total,
        "partner_inventory_added": added_inv,
        "partner_inventory_total": inv_total,
    }


if __name__ == "__main__":
    stats = import_into_sqlite()
    print("Real catalog imported:", stats)
