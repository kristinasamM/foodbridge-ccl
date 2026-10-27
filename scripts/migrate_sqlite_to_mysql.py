#!/usr/bin/env python3
"""
FoodBridge SQLite to MySQL RDS Migration Utility
Preserves primary keys, foreign keys, timestamps, and password hashes.
Safe to rerun: Idempotent with pre-flight content conflict detection, dry-run support,
and single-transaction atomicity across all tables.
"""

import argparse
import os
import sqlite3
import sys
from datetime import datetime

try:
    from sqlalchemy import create_engine, text
    from sqlalchemy.engine import URL
except ImportError:
    print("[ERROR] SQLAlchemy is required. Run: pip install SQLAlchemy PyMySQL cryptography")
    sys.exit(1)


class MigrationConflictError(Exception):
    """Raised when existing target records conflict with source data."""
    pass


def parse_args():
    parser = argparse.ArgumentParser(description="Migrate FoodBridge SQLite data to MySQL RDS")
    parser.add_argument(
        "--sqlite-path",
        default=os.path.join(os.path.dirname(__file__), "..", "instance", "foodbridge.db"),
        help="Path to source SQLite database file"
    )
    parser.add_argument(
        "--mysql-uri",
        default=os.environ.get("DATABASE_URL"),
        help="Target MySQL connection URI (or via DATABASE_URL environment variable)"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Simulate migration and report differences without writing to target database"
    )
    return parser.parse_args()


def mask_uri(uri):
    """Mask password in connection URI for safe logging."""
    if not uri:
        return "<EMPTY>"
    try:
        if "@" in uri and ":" in uri:
            prefix, rest = uri.split("@", 1)
            protocol_user, _ = prefix.rsplit(":", 1)
            return f"{protocol_user}:***@{rest}"
    except Exception:
        pass
    return "<MASKED_URI>"


def parse_timestamp(val):
    """Normalize SQLite timestamp string or datetime object for database insertion."""
    if val is None:
        return None
    if isinstance(val, datetime):
        return val
    # Handle string ISO format timestamps from SQLite
    try:
        val_clean = val.split("+")[0].split(".")[0].replace("T", " ")
        return datetime.strptime(val_clean, "%Y-%m-%d %H:%M:%S")
    except Exception:
        return val


def migrate_data(sqlite_path, mysql_uri, dry_run=False):
    abs_sqlite = os.path.abspath(sqlite_path)
    if not os.path.exists(abs_sqlite):
        print(f"[ERROR] Source SQLite database not found at: {abs_sqlite}")
        return False

    if not mysql_uri:
        print("[ERROR] Target MySQL URI not provided. Set DATABASE_URL or pass --mysql-uri.")
        return False

    print("==========================================================")
    print("FoodBridge SQLite -> MySQL RDS Data Migration")
    print(f"Source SQLite:  {abs_sqlite}")
    print(f"Target Database:{mask_uri(mysql_uri)}")
    print(f"Execution Mode: {'DRY RUN (Preview Only)' if dry_run else 'ATOMIC LIVE MIGRATION'}")
    print("==========================================================")

    # 1. Connect to SQLite in read-only mode to guarantee zero modification
    sqlite_conn = sqlite3.connect(f"file:{abs_sqlite}?mode=ro", uri=True)
    sqlite_conn.row_factory = sqlite3.Row
    sqlite_cur = sqlite_conn.cursor()

    # 2. Connect to Target Database Engine
    engine_kwargs = {"pool_pre_ping": True}
    if mysql_uri.startswith("mysql"):
        engine_kwargs["pool_recycle"] = 280
    engine = create_engine(mysql_uri, **engine_kwargs)

    try:
        # Single atomic transaction context for all tables (or connect() for dry-run)
        conn_context = engine.connect() if dry_run else engine.begin()
        with conn_context as target_conn:
            # Pre-flight Check: Ensure target tables exist
            if mysql_uri.startswith("mysql"):
                table_check = target_conn.execute(text("SHOW TABLES LIKE 'users'")).fetchall()
            else:
                table_check = target_conn.execute(text("SELECT name FROM sqlite_master WHERE type='table' AND name='users'")).fetchall()

            if not table_check:
                print("[ERROR] Target database has not been initialized with tables yet.")
                print("        Please ensure database tables exist (e.g. via 'flask init-db' or 'db.create_all()') before migrating.")
                return False

            conflicts = []

            # ------------------------------------------------------------------
            # A. INSPECT USERS
            # ------------------------------------------------------------------
            print("\n--- 1. Inspecting Users ---")
            sqlite_cur.execute("SELECT id, name, email, password_hash, role FROM users ORDER BY id ASC")
            sqlite_users = sqlite_cur.fetchall()
            print(f"Found {len(sqlite_users)} user(s) in source SQLite.")

            users_to_insert = []
            for u in sqlite_users:
                existing = target_conn.execute(
                    text("SELECT id, name, email, password_hash, role FROM users WHERE id = :id OR email = :email"),
                    {"id": u["id"], "email": u["email"]}
                ).mappings().fetchone()

                if existing:
                    # Check if exact identity match
                    if existing["id"] == u["id"] and existing["email"].lower() == u["email"].lower():
                        # Verify content match (idempotent repeat run)
                        diffs = []
                        if existing["name"] != u["name"]:
                            diffs.append(f"name: target='{existing['name']}', source='{u['name']}'")
                        if existing["role"] != u["role"]:
                            diffs.append(f"role: target='{existing['role']}', source='{u['role']}'")
                        if existing["password_hash"] != u["password_hash"]:
                            diffs.append("password_hash differs")

                        if diffs:
                            conflict_msg = f"User #{u['id']} ({u['email']}) exists in target with conflicting content: {', '.join(diffs)}"
                            conflicts.append(conflict_msg)
                            print(f"  [CONTENT CONFLICT] {conflict_msg}")
                        else:
                            print(f"  [IDEMPOTENT] User #{u['id']} ({u['email']}) matches target record identically. Safe to skip.")
                    else:
                        conflict_msg = f"User #{u['id']} ({u['email']}) collisions with target record #{existing['id']} ({existing['email']})"
                        conflicts.append(conflict_msg)
                        print(f"  [COLLISION CONFLICT] {conflict_msg}")
                else:
                    users_to_insert.append(u)
                    print(f"  [NEW] User #{u['id']}: {u['name']} <{u['email']}> ({u['role']}) queued for import.")

            # ------------------------------------------------------------------
            # B. INSPECT DONATIONS
            # ------------------------------------------------------------------
            print("\n--- 2. Inspecting Donations ---")
            sqlite_cur.execute("""
                SELECT id, donor_id, food_name, category, quantity, pickup_location,
                       available_until, description, image_filename, status, created_at
                FROM donations ORDER BY id ASC
            """)
            sqlite_donations = sqlite_cur.fetchall()
            print(f"Found {len(sqlite_donations)} donation(s) in source SQLite.")

            donations_to_insert = []
            for d in sqlite_donations:
                existing = target_conn.execute(
                    text("""
                        SELECT id, donor_id, food_name, category, quantity, pickup_location, status
                        FROM donations WHERE id = :id
                    """),
                    {"id": d["id"]}
                ).mappings().fetchone()

                if existing:
                    diffs = []
                    if existing["donor_id"] != d["donor_id"]:
                        diffs.append(f"donor_id: target={existing['donor_id']}, source={d['donor_id']}")
                    if existing["food_name"] != d["food_name"]:
                        diffs.append(f"food_name: target='{existing['food_name']}', source='{d['food_name']}'")
                    if existing["quantity"] != d["quantity"]:
                        diffs.append(f"quantity: target={existing['quantity']}, source={d['quantity']}")
                    if existing["status"] != d["status"]:
                        diffs.append(f"status: target='{existing['status']}', source='{d['status']}'")

                    if diffs:
                        conflict_msg = f"Donation #{d['id']} exists in target with conflicting content: {', '.join(diffs)}"
                        conflicts.append(conflict_msg)
                        print(f"  [CONTENT CONFLICT] {conflict_msg}")
                    else:
                        print(f"  [IDEMPOTENT] Donation #{d['id']} ('{d['food_name']}') matches target identically. Safe to skip.")
                else:
                    donations_to_insert.append(d)
                    print(f"  [NEW] Donation #{d['id']}: '{d['food_name']}' (Donor #{d['donor_id']}, Status: {d['status']}) queued for import.")

            # ------------------------------------------------------------------
            # C. INSPECT RESERVATIONS
            # ------------------------------------------------------------------
            print("\n--- 3. Inspecting Reservations ---")
            sqlite_cur.execute("""
                SELECT id, donation_id, ngo_id, reserved_at, pickup_status
                FROM reservations ORDER BY id ASC
            """)
            sqlite_reservations = sqlite_cur.fetchall()
            print(f"Found {len(sqlite_reservations)} reservation(s) in source SQLite.")

            reservations_to_insert = []
            for r in sqlite_reservations:
                existing = target_conn.execute(
                    text("""
                        SELECT id, donation_id, ngo_id, pickup_status
                        FROM reservations WHERE id = :id OR donation_id = :donation_id
                    """),
                    {"id": r["id"], "donation_id": r["donation_id"]}
                ).mappings().fetchone()

                if existing:
                    if existing["id"] == r["id"] and existing["donation_id"] == r["donation_id"]:
                        diffs = []
                        if existing["ngo_id"] != r["ngo_id"]:
                            diffs.append(f"ngo_id: target={existing['ngo_id']}, source={r['ngo_id']}")
                        if existing["pickup_status"] != r["pickup_status"]:
                            diffs.append(f"pickup_status: target='{existing['pickup_status']}', source='{r['pickup_status']}'")

                        if diffs:
                            conflict_msg = f"Reservation #{r['id']} (Donation #{r['donation_id']}) exists with conflicting content: {', '.join(diffs)}"
                            conflicts.append(conflict_msg)
                            print(f"  [CONTENT CONFLICT] {conflict_msg}")
                        else:
                            print(f"  [IDEMPOTENT] Reservation #{r['id']} (Donation #{r['donation_id']}) matches target identically. Safe to skip.")
                    else:
                        conflict_msg = f"Reservation #{r['id']} (Donation #{r['donation_id']}) collisions with target record #{existing['id']} (Donation #{existing['donation_id']})"
                        conflicts.append(conflict_msg)
                        print(f"  [COLLISION CONFLICT] {conflict_msg}")
                else:
                    reservations_to_insert.append(r)
                    print(f"  [NEW] Reservation #{r['id']}: Donation #{r['donation_id']} by NGO #{r['ngo_id']} queued for import.")

            # ------------------------------------------------------------------
            # D. VALIDATE CONFLICTS BEFORE ANY WRITE
            # ------------------------------------------------------------------
            if conflicts:
                print("\n" + "=" * 58)
                print(f"[ABORT] Detected {len(conflicts)} data conflict(s)! Migration halted to prevent data corruption:")
                for c in conflicts:
                    print(f"  - {c}")
                print("=" * 58)
                raise MigrationConflictError(f"Migration aborted due to {len(conflicts)} data conflict(s). No records were modified.")

            # ------------------------------------------------------------------
            # E. EXECUTE ATOMIC TRANSACTION (WRITES)
            # ------------------------------------------------------------------
            total_new = len(users_to_insert) + len(donations_to_insert) + len(reservations_to_insert)

            if dry_run:
                print("\n--- Dry Run Completed Successfully ---")
                print(f"Records that would be inserted: Users: {len(users_to_insert)}, Donations: {len(donations_to_insert)}, Reservations: {len(reservations_to_insert)}")
                print("[DRY RUN] Zero database writes performed.")
                return True

            if total_new == 0:
                print("\n[IDEMPOTENT] Target database is already completely up to date with source SQLite. No writes required.")
                return True

            print(f"\n--- Executing Atomic Write Transaction ({total_new} new records) ---")
            # 1. Insert Users
            for u in users_to_insert:
                target_conn.execute(
                    text("""
                        INSERT INTO users (id, name, email, password_hash, role)
                        VALUES (:id, :name, :email, :password_hash, :role)
                    """),
                    {
                        "id": u["id"],
                        "name": u["name"],
                        "email": u["email"],
                        "password_hash": u["password_hash"],
                        "role": u["role"]
                    }
                )
            print(f"  [COMMITTED] Inserted {len(users_to_insert)} user(s).")

            # 2. Insert Donations
            for d in donations_to_insert:
                target_conn.execute(
                    text("""
                        INSERT INTO donations (
                            id, donor_id, food_name, category, quantity, pickup_location,
                            available_until, description, image_filename, status, created_at
                        ) VALUES (
                            :id, :donor_id, :food_name, :category, :quantity, :pickup_location,
                            :available_until, :description, :image_filename, :status, :created_at
                        )
                    """),
                    {
                        "id": d["id"],
                        "donor_id": d["donor_id"],
                        "food_name": d["food_name"],
                        "category": d["category"],
                        "quantity": d["quantity"],
                        "pickup_location": d["pickup_location"],
                        "available_until": parse_timestamp(d["available_until"]),
                        "description": d["description"],
                        "image_filename": d["image_filename"],
                        "status": d["status"],
                        "created_at": parse_timestamp(d["created_at"])
                    }
                )
            print(f"  [COMMITTED] Inserted {len(donations_to_insert)} donation(s).")

            # 3. Insert Reservations
            for r in reservations_to_insert:
                target_conn.execute(
                    text("""
                        INSERT INTO reservations (id, donation_id, ngo_id, reserved_at, pickup_status)
                        VALUES (:id, :donation_id, :ngo_id, :reserved_at, :pickup_status)
                    """),
                    {
                        "id": r["id"],
                        "donation_id": r["donation_id"],
                        "ngo_id": r["ngo_id"],
                        "reserved_at": parse_timestamp(r["reserved_at"]),
                        "pickup_status": r["pickup_status"]
                    }
                )
            print(f"  [COMMITTED] Inserted {len(reservations_to_insert)} reservation(s).")

        # ------------------------------------------------------------------
        # F. POST-MIGRATION VERIFICATION
        # ------------------------------------------------------------------
        if not dry_run:
            print("\n[SUCCESS] Atomic transaction committed successfully.")
            with engine.connect() as verify_conn:
                m_users = verify_conn.execute(text("SELECT COUNT(*) FROM users")).scalar()
                m_donations = verify_conn.execute(text("SELECT COUNT(*) FROM donations")).scalar()
                m_reservations = verify_conn.execute(text("SELECT COUNT(*) FROM reservations")).scalar()

                print("\n--- Post-Migration Record Counts ---")
                print(f"  Users:        {m_users}")
                print(f"  Donations:    {m_donations}")
                print(f"  Reservations: {m_reservations}")

    finally:
        sqlite_conn.close()

    print("\n[COMPLETE] Migration completed safely. Source SQLite remained untouched.")
    return True


if __name__ == "__main__":
    args = parse_args()
    try:
        success = migrate_data(args.sqlite_path, args.mysql_uri, dry_run=args.dry_run)
        if not success:
            sys.exit(1)
    except MigrationConflictError as e:
        print(f"\n[ABORTED] {e}")
        sys.exit(2)
    except Exception as ex:
        print(f"\n[UNEXPECTED ERROR] {ex}")
        sys.exit(1)
