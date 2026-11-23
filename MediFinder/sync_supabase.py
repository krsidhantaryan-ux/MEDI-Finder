"""
Sync local `MediFinder/database.db` (shops, inventory, reservations, and all 11,407 real
Indian Branded + PMBJP Jan Aushadhi catalog rows) into Supabase PostgreSQL.

Usage:
    SUPABASE_DB_URL="postgresql://postgres.mqgejhfudhnliyyzomur:<PASSWORD>@aws-0-ap-northeast-1.pooler.supabase.com:5432/postgres" \
        python MediFinder/sync_supabase.py
"""

import os
import sqlite3
import sys

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SQLITE_PATH = os.path.join(BASE_DIR, "database.db")


def sync():
    pg_url = (
        os.environ.get("SUPABASE_DB_URL")
        or os.environ.get("MEDIFINDER_POSTGRES_URL")
        or os.environ.get("DATABASE_URL")
        or ""
    ).strip()
    if pg_url.startswith("postgres://"):
        pg_url = "postgresql://" + pg_url[len("postgres://"):]
    if not pg_url.startswith("postgresql://"):
        print("Set SUPABASE_DB_URL (postgresql://...) before running sync_supabase.py.", file=sys.stderr)
        return 1

    import psycopg  # type: ignore

    src = sqlite3.connect(SQLITE_PATH)
    src.row_factory = sqlite3.Row

    with psycopg.connect(pg_url) as pg:
        with pg.cursor() as cur:
            cur.execute("TRUNCATE public.reservations, public.inventory, public.shops, public.medicine_catalog RESTART IDENTITY CASCADE;")

            shops = src.execute(
                "SELECT id, name, city, password, lat, lng, status, license_number, license_image, gst_certificate, shop_photo, phone, opening_hours, address FROM shops ORDER BY id"
            ).fetchall()
            cur.executemany(
                """
                INSERT INTO public.shops
                    (id, name, city, password, lat, lng, status, license_number, license_image, gst_certificate, shop_photo, phone, opening_hours, address)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                [tuple(r) for r in shops],
            )
            cur.execute("SELECT setval(pg_get_serial_sequence('public.shops', 'id'), COALESCE((SELECT MAX(id) FROM public.shops), 1));")

            inv = src.execute(
                "SELECT id, shop_id, med_name, salt_composition, price, stock_quantity, dosage, rx_required, expiry_date FROM inventory ORDER BY id"
            ).fetchall()
            cur.executemany(
                """
                INSERT INTO public.inventory
                    (id, shop_id, med_name, salt_composition, price, stock_quantity, dosage, rx_required, expiry_date)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                [tuple(r) for r in inv],
            )
            cur.execute("SELECT setval(pg_get_serial_sequence('public.inventory', 'id'), COALESCE((SELECT MAX(id) FROM public.inventory), 1));")

            catalog = src.execute(
                "SELECT med_name, manufacturer, salt_composition, pack_size, mrp, is_generic, rx_required, source FROM medicine_catalog ORDER BY id"
            ).fetchall()
            cur.executemany(
                """
                INSERT INTO public.medicine_catalog
                    (med_name, manufacturer, salt_composition, pack_size, mrp, is_generic, rx_required, source)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                """,
                [tuple(r) for r in catalog],
            )
        pg.commit()

    src.close()
    print(f"Synced {len(shops)} shops, {len(inv)} inventory items, and {len(catalog)} real catalog medicines to Supabase.")
    return 0


if __name__ == "__main__":
    raise SystemExit(sync())
