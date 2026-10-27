#!/usr/bin/env python3
"""
FoodBridge Automated Donation Expiration Script
File: /var/www/foodbridge/scripts/expire_donations.py

Usage:
  python3 expire_donations.py            # Defaults to DRY-RUN mode (safe, read-only)
  python3 expire_donations.py --dry-run  # Explicit DRY-RUN mode
  python3 expire_donations.py --live     # Live execution (updates MySQL and notifies SNS)

Features:
- Defaults to safe DRY-RUN mode
- Reuses Flask app context, SQLAlchemy models, and Secrets Manager MySQL connection
- Strict timezone consistency (UTC naive matching MySQL DATETIME)
- Atomic conditional updates (prevents race conditions with concurrent reservations)
- Non-blocking process locking (prevents overlapping executions via fcntl)
- Post-commit SNS notifications (ensures DB consistency before publishing)
- Structured JSON output for AWS Lambda / SSM Run Command parsing
- Zero credential exposure
"""

import argparse
import json
import os
import sys
from datetime import datetime, timezone, timedelta
try:
    from zoneinfo import ZoneInfo
    IST_TZ = ZoneInfo("Asia/Kolkata")
except Exception:
    IST_TZ = timezone(timedelta(hours=5, minutes=30))

# Ensure project root is in sys.path
PROJECT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if PROJECT_DIR not in sys.path:
    sys.path.insert(0, PROJECT_DIR)

# Also check production /var/www/foodbridge path
if "/var/www/foodbridge" not in sys.path:
    sys.path.insert(0, "/var/www/foodbridge")

# Load environment file if present (EC2 production)
for env_path in ["/var/www/foodbridge/.env", os.path.join(PROJECT_DIR, ".env")]:
    if os.path.exists(env_path):
        with open(env_path, "r") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    if k.strip() not in os.environ:
                        os.environ[k.strip()] = v.strip()
        break

from app import app, db, Donation, Reservation, publish_sns_notification, build_sns_message

LOCK_FILE_PATH = "/tmp/foodbridge_expiry.lock"


def acquire_process_lock():
    """
    Acquires an exclusive, non-blocking file lock to prevent overlapping runs.
    Returns the open file descriptor or None if locked by another process.
    """
    try:
        import fcntl
        lock_fd = open(LOCK_FILE_PATH, "w")
        fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        return lock_fd
    except (BlockingIOError, PermissionError):
        return None
    except ImportError:
        # Windows / local development fallback (fcntl not available on Windows)
        return open(LOCK_FILE_PATH, "w")


def release_process_lock(lock_fd):
    """Releases the process lock and closes the file descriptor."""
    if lock_fd:
        try:
            import fcntl
            fcntl.flock(lock_fd, fcntl.LOCK_UN)
        except (ImportError, Exception):
            pass
        try:
            lock_fd.close()
        except Exception:
            pass


def get_eligible_expired_donations(now_ref=None):
    """
    Queries for all donations eligible for expiration:
    - status must be strictly 'AVAILABLE'
    - available_until must be earlier than or equal to now_ref (IST naive)
    - Preserves RESERVED, COMPLETED, and already EXPIRED records
    """
    if now_ref is None:
        now_ref = datetime.now(IST_TZ).replace(tzinfo=None)

    return (
        Donation.query.filter(
            Donation.status == "AVAILABLE",
            Donation.available_until <= now_ref,
        )
        .order_by(Donation.available_until.asc())
        .all()
    )


def process_expiration(is_live=False):
    """
    Core expiration logic.
    If is_live is False, performs a DRY-RUN inspection only.
    If is_live is True, atomically updates MySQL and publishes SNS alerts.
    """
    lock_fd = None
    ctx_manager = None
    if is_live:
        lock_fd = acquire_process_lock()
        if lock_fd is None:
            result = {
                "status": "SKIPPED",
                "mode": "LIVE",
                "message": "Another expiration process is currently running. Exiting cleanly.",
                "timestamp": datetime.now(IST_TZ).isoformat(),
            }
            print(json.dumps(result, indent=2))
            return result

    try:
        # Match naive IST values stored in MySQL
        now_ist = datetime.now(IST_TZ).replace(tzinfo=None)
        timestamp_str = datetime.now(IST_TZ).strftime("%Y-%m-%d %H:%M:%S IST")

        from flask import has_app_context
        ctx_manager = None if has_app_context() else app.app_context()
        if ctx_manager:
            ctx_manager.__enter__()

        eligible = get_eligible_expired_donations(now_ist)
        total_eligible = len(eligible)

        eligible_summary = [
            {
                "id": d.id,
                "food_name": d.food_name,
                "category": d.category,
                "quantity": d.quantity,
                "available_until": d.available_until.isoformat() if d.available_until else None,
                "status_before": d.status,
            }
            for d in eligible
        ]

        if not is_live:
            # -------------------------------------------------------------
            # DRY-RUN MODE (Default & Safe - Read-Only)
            # -------------------------------------------------------------
            result = {
                "status": "SUCCESS",
                "mode": "DRY_RUN",
                "timestamp": timestamp_str,
                "eligible_count": total_eligible,
                "eligible_donations": eligible_summary,
                "database_updated": False,
                "notifications_sent": 0,
                "message": f"DRY-RUN completed. Found {total_eligible} eligible expired donation(s). No changes made.",
            }
            print(json.dumps(result, indent=2))
            return result

        # -----------------------------------------------------------------
        # LIVE EXECUTION MODE (Only when --live is explicitly passed)
        # -----------------------------------------------------------------
        if total_eligible == 0:
            result = {
                "status": "SUCCESS",
                "mode": "LIVE",
                "timestamp": timestamp_str,
                "eligible_count": 0,
                "updated_count": 0,
                "notifications_sent": 0,
                "message": "No eligible expired donations found. Nothing to update.",
            }
            print(json.dumps(result, indent=2))
            return result

        successfully_updated_ids = []
        for d in eligible:
            # Atomic conditional update prevents race condition if reserved concurrently
            rows_affected = (
                db.session.query(Donation)
                .filter(
                    Donation.id == d.id,
                    Donation.status == "AVAILABLE",
                )
                .update({"status": "EXPIRED"}, synchronize_session=False)
            )
            if rows_affected == 1:
                successfully_updated_ids.append(d.id)

        # Commit database changes strictly BEFORE sending notifications
        db.session.commit()
        updated_count = len(successfully_updated_ids)

        # Post-commit SNS Notification Loop
        notification_results = []
        sns_success_count = 0
        sns_failure_count = 0

        for donation_id in successfully_updated_ids:
            d_record = db.session.get(Donation, donation_id)
            success, msg_id = publish_sns_notification("DONATION_EXPIRED", donation=d_record)
            if success:
                sns_success_count += 1
                notification_results.append({
                    "donation_id": donation_id,
                    "food_name": d_record.food_name,
                    "sns_published": True,
                    "message_id": msg_id,
                    "error": None,
                })
            else:
                sns_failure_count += 1
                notification_results.append({
                    "donation_id": donation_id,
                    "food_name": d_record.food_name,
                    "sns_published": False,
                    "message_id": None,
                    "error": "SNS publish failed (see application logs)",
                })

        result = {
            "status": "SUCCESS",
            "mode": "LIVE",
            "timestamp": timestamp_str,
            "eligible_count": total_eligible,
            "updated_count": updated_count,
            "updated_ids": successfully_updated_ids,
            "notifications_sent": sns_success_count,
            "notifications_failed": sns_failure_count,
            "notification_details": notification_results,
            "note": "Amazon SNS provides at-least-once delivery; exactly-once delivery is not claimed without persistent event tracking.",
            "message": f"Successfully transitioned {updated_count} donation(s) to EXPIRED. SNS notifications sent: {sns_success_count}.",
        }
        print(json.dumps(result, indent=2))
        return result

    except Exception as e:
        if is_live:
            db.session.rollback()
        err_result = {
            "status": "ERROR",
            "mode": "LIVE" if is_live else "DRY_RUN",
            "error_type": type(e).__name__,
            "error_message": str(e),
        }
        print(json.dumps(err_result, indent=2))
        return err_result

    finally:
        if ctx_manager:
            try:
                ctx_manager.__exit__(None, None, None)
            except Exception:
                pass
        if lock_fd:
            release_process_lock(lock_fd)


def main():
    parser = argparse.ArgumentParser(
        description="FoodBridge Automated Donation Expiration Utility",
        epilog="Default mode is DRY-RUN for production safety. Pass --live to perform actual updates."
    )
    group = parser.add_mutually_exclusive_group()
    group.add_argument(
        "--dry-run",
        action="store_true",
        default=True,
        help="Inspect eligible donations without modifying database or sending SNS messages (DEFAULT)."
    )
    group.add_argument(
        "--live",
        action="store_true",
        help="Execute live atomic database updates and publish SNS notifications."
    )

    args = parser.parse_args()
    is_live = bool(args.live)
    process_expiration(is_live=is_live)


if __name__ == "__main__":
    main()
