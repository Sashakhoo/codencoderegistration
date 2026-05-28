import os
import sqlite3
from pathlib import Path

import psycopg


BASE_DIR = Path(__file__).resolve().parent
SQLITE_PATH = Path(os.getenv("WORKSHOP_DB", BASE_DIR / "workshop.db"))
DATABASE_URL = os.getenv("DATABASE_URL")

TABLES = [
    "workshops",
    "workshop_materials",
    "workshop_schedule",
    "workshop_announcements",
    "workshop_registrations",
    "workshop_progress",
]


def placeholders(count):
    return ", ".join(["%s"] * count)


def main():
    if not DATABASE_URL:
        raise SystemExit("DATABASE_URL is required.")
    if not SQLITE_PATH.exists():
        raise SystemExit(f"SQLite database not found: {SQLITE_PATH}")

    sqlite_conn = sqlite3.connect(SQLITE_PATH)
    sqlite_conn.row_factory = sqlite3.Row

    with psycopg.connect(DATABASE_URL) as pg_conn:
        for table in TABLES:
            rows = [dict(row) for row in sqlite_conn.execute(f"SELECT * FROM {table}")]
            if not rows:
                continue

            columns = list(rows[0].keys())
            quoted_columns = ", ".join(columns)
            update_columns = [column for column in columns if column != "id"]
            updates = ", ".join(f"{column} = EXCLUDED.{column}" for column in update_columns)

            sql = (
                f"INSERT INTO {table} ({quoted_columns}) "
                f"VALUES ({placeholders(len(columns))}) "
                f"ON CONFLICT (id) DO UPDATE SET {updates}"
            )
            values = [tuple(row[column] for column in columns) for row in rows]
            with pg_conn.cursor() as cur:
                cur.executemany(sql, values)

            sequence_name = f"{table}_id_seq"
            pg_conn.execute(
                "SELECT setval(%s, COALESCE((SELECT MAX(id) FROM " + table + "), 1), true)",
                (sequence_name,),
            )

            print(f"Migrated {len(rows)} rows from {table}.")

    sqlite_conn.close()


if __name__ == "__main__":
    main()
