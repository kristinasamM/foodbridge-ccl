#!/usr/bin/env python3
"""
Automated Test Suite for FoodBridge Donation Expiration Logic
File: test_step19e_expiry_suite.py

Tests:
1. Eligibility: AVAILABLE + past timestamp = ELIGIBLE
2. Eligibility: AVAILABLE + future timestamp = NOT ELIGIBLE
3. State Preservation: RESERVED with past timestamp is PRESERVED (NOT ELIGIBLE)
4. State Preservation: COMPLETED with past timestamp is PRESERVED (NOT ELIGIBLE)
5. State Preservation: EXPIRED with past timestamp is PRESERVED (NOT ELIGIBLE)
6. Timezone Boundary: exact match (now_utc) is ELIGIBLE
7. Timezone Boundary: 1 second in future is NOT ELIGIBLE
8. Timezone Boundary: 1 second in past is ELIGIBLE
9. DRY-RUN Safety: No database updates, no SNS calls
10. Idempotency: Repeated live runs do not duplicate transitions or notifications
11. Concurrency: Process locking prevents overlapping execution
12. SNS Partial Failure: Honest reporting when SNS publish encounters an error
"""

import os
import sys
import unittest
from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock, patch

from sqlalchemy import create_engine
from sqlalchemy.orm import scoped_session, sessionmaker

# Ensure project root and scripts in sys.path
PROJECT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SCRIPTS_DIR = os.path.join(PROJECT_DIR, "scripts")
for p in [PROJECT_DIR, SCRIPTS_DIR, "/var/www/foodbridge", "/var/www/foodbridge/scripts"]:
    if p not in sys.path:
        sys.path.insert(0, p)

import app
from app import app as flask_app, db, Donation, Reservation
import expire_donations
from expire_donations import (
    get_eligible_expired_donations,
    process_expiration,
    acquire_process_lock,
    release_process_lock,
)


class Step19EExpiryTestSuite(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Create an isolated in-memory SQLite database
        cls.engine = create_engine("sqlite:///:memory:")
        cls.connection = cls.engine.connect()
        db.metadata.create_all(bind=cls.connection)
        cls.TestSession = scoped_session(sessionmaker(bind=cls.connection))

    @classmethod
    def tearDownClass(cls):
        cls.TestSession.remove()
        db.metadata.drop_all(bind=cls.connection)
        cls.connection.close()
        cls.engine.dispose()

    def setUp(self):
        # Patch db.session to use isolated in-memory session
        self.session_patcher = patch.object(db, "session", self.TestSession)
        self.session_patcher.start()

        self.app_context = flask_app.app_context()
        self.app_context.push()

        # Clean tables
        self.TestSession.query(Reservation).delete()
        self.TestSession.query(Donation).delete()
        self.TestSession.commit()

        self.now_utc = datetime(2026, 10, 21, 12, 0, 0)

        # Seed test donations
        self.d_eligible = Donation(
            id=101,
            donor_id=2,
            food_name="Buffet Rice Trays",
            category="Cooked Food",
            quantity=30,
            pickup_location="Banquet Hall A",
            available_until=self.now_utc - timedelta(hours=2),
            status="AVAILABLE",
        )
        self.d_future = Donation(
            id=102,
            donor_id=2,
            food_name="Fresh Bread",
            category="Bakery",
            quantity=15,
            pickup_location="Bakery 1",
            available_until=self.now_utc + timedelta(hours=5),
            status="AVAILABLE",
        )
        self.d_reserved = Donation(
            id=103,
            donor_id=2,
            food_name="Packaged Meals",
            category="Packaged Food",
            quantity=20,
            pickup_location="Hub 2",
            available_until=self.now_utc - timedelta(hours=1),
            status="RESERVED",
        )
        self.d_completed = Donation(
            id=104,
            donor_id=2,
            food_name="Apples Box",
            category="Fruits / Vegetables",
            quantity=50,
            pickup_location="Market 3",
            available_until=self.now_utc - timedelta(days=1),
            status="COMPLETED",
        )
        self.d_already_expired = Donation(
            id=105,
            donor_id=2,
            food_name="Salad Trays",
            category="Cooked Food",
            quantity=10,
            pickup_location="Kitchen 4",
            available_until=self.now_utc - timedelta(days=2),
            status="EXPIRED",
        )

        self.TestSession.add_all([
            self.d_eligible,
            self.d_future,
            self.d_reserved,
            self.d_completed,
            self.d_already_expired,
        ])
        self.TestSession.commit()

    def tearDown(self):
        self.TestSession.remove()
        self.app_context.pop()
        self.session_patcher.stop()

    # --------------------------------------------------------------------------
    # 1 & 2. Eligibility Verification
    # --------------------------------------------------------------------------
    def test_eligibility_available_and_past(self):
        eligible = get_eligible_expired_donations(self.now_utc)
        eligible_ids = [d.id for d in eligible]
        self.assertIn(101, eligible_ids, "Donation 101 (AVAILABLE + past) must be eligible")
        self.assertNotIn(102, eligible_ids, "Donation 102 (AVAILABLE + future) must NOT be eligible")

    # --------------------------------------------------------------------------
    # 3, 4, 5. Preservation of Non-Eligible States
    # --------------------------------------------------------------------------
    def test_preserves_reserved_completed_expired(self):
        eligible = get_eligible_expired_donations(self.now_utc)
        eligible_ids = [d.id for d in eligible]
        self.assertNotIn(103, eligible_ids, "Donation 103 (RESERVED) must be preserved")
        self.assertNotIn(104, eligible_ids, "Donation 104 (COMPLETED) must be preserved")
        self.assertNotIn(105, eligible_ids, "Donation 105 (already EXPIRED) must not be re-selected")

    # --------------------------------------------------------------------------
    # 6, 7, 8. Timezone Boundary Tests
    # --------------------------------------------------------------------------
    def test_timezone_exact_boundary(self):
        d_exact = Donation(
            id=106,
            donor_id=2,
            food_name="Exact Boundary Item",
            category="Other",
            quantity=5,
            pickup_location="Test Hub",
            available_until=self.now_utc,
            status="AVAILABLE",
        )
        self.TestSession.add(d_exact)
        self.TestSession.commit()

        eligible = get_eligible_expired_donations(self.now_utc)
        eligible_ids = [d.id for d in eligible]
        self.assertIn(106, eligible_ids, "Exact boundary (<= now_utc) must be eligible")

    def test_timezone_future_boundary_plus_one_second(self):
        d_future_sec = Donation(
            id=107,
            donor_id=2,
            food_name="One Sec In Future",
            category="Other",
            quantity=5,
            pickup_location="Test Hub",
            available_until=self.now_utc + timedelta(seconds=1),
            status="AVAILABLE",
        )
        self.TestSession.add(d_future_sec)
        self.TestSession.commit()

        eligible = get_eligible_expired_donations(self.now_utc)
        eligible_ids = [d.id for d in eligible]
        self.assertNotIn(107, eligible_ids, "Timestamp +1 second in future must NOT be eligible")

    def test_timezone_past_boundary_minus_one_second(self):
        d_past_sec = Donation(
            id=108,
            donor_id=2,
            food_name="One Sec In Past",
            category="Other",
            quantity=5,
            pickup_location="Test Hub",
            available_until=self.now_utc - timedelta(seconds=1),
            status="AVAILABLE",
        )
        self.TestSession.add(d_past_sec)
        self.TestSession.commit()

        eligible = get_eligible_expired_donations(self.now_utc)
        eligible_ids = [d.id for d in eligible]
        self.assertIn(108, eligible_ids, "Timestamp -1 second in past must be eligible")

    # --------------------------------------------------------------------------
    # 9. DRY-RUN Safety Guarantee
    # --------------------------------------------------------------------------
    @patch("expire_donations.publish_sns_notification")
    def test_dry_run_safety(self, mock_sns):
        with patch("expire_donations.datetime") as mock_dt:
            mock_dt.now.return_value = self.now_utc
            result = process_expiration(is_live=False)

        self.assertEqual(result["status"], "SUCCESS")
        self.assertEqual(result["mode"], "DRY_RUN")
        self.assertEqual(result["eligible_count"], 1)
        self.assertFalse(result["database_updated"])
        self.assertEqual(result["notifications_sent"], 0)

        # Verify DB status was NOT changed
        d101 = self.TestSession.query(Donation).filter(Donation.id == 101).first()
        self.assertIsNotNone(d101, "Donation 101 must exist")
        self.assertEqual(d101.status, "AVAILABLE", "DRY-RUN must NOT alter database status")

        # Verify SNS was NOT called
        mock_sns.assert_not_called()

    # --------------------------------------------------------------------------
    # 10. Idempotency & Live Transition
    # --------------------------------------------------------------------------
    @patch("expire_donations.publish_sns_notification", return_value=(True, "mock-msg-id-123"))
    def test_live_execution_idempotency(self, mock_sns):
        with patch("expire_donations.datetime") as mock_dt:
            mock_dt.now.return_value = self.now_utc

            # Run 1: Should transition donation 101
            res1 = process_expiration(is_live=True)
            self.assertEqual(res1["status"], "SUCCESS")
            self.assertEqual(res1["updated_count"], 1)
            self.assertEqual(res1["notifications_sent"], 1)

            d101 = self.TestSession.get(Donation, 101)
            self.assertEqual(d101.status, "EXPIRED", "Donation 101 must be EXPIRED in DB")

            # Run 2: Immediate second run must find 0 eligible (idempotency)
            res2 = process_expiration(is_live=True)
            self.assertEqual(res2["status"], "SUCCESS")
            self.assertEqual(res2["eligible_count"], 0)
            self.assertEqual(res2["updated_count"], 0)
            self.assertEqual(res2["notifications_sent"], 0)

            # SNS was called only once across both runs
            mock_sns.assert_called_once()

    # --------------------------------------------------------------------------
    # 11. Concurrency: Process Locking
    # --------------------------------------------------------------------------
    def test_process_lock_prevents_concurrent_runs(self):
        lock_fd = acquire_process_lock()
        second_lock = None
        try:
            second_lock = acquire_process_lock()
            if sys.platform != "win32":
                self.assertIsNone(second_lock, "Second lock acquisition must fail while held")
        finally:
            if second_lock:
                release_process_lock(second_lock)
            release_process_lock(lock_fd)

    # --------------------------------------------------------------------------
    # 12. SNS Partial Failure Handling
    # --------------------------------------------------------------------------
    @patch("expire_donations.publish_sns_notification")
    def test_sns_failure_does_not_rollback_db(self, mock_sns):
        mock_sns.return_value = (False, None)

        with patch("expire_donations.datetime") as mock_dt:
            mock_dt.now.return_value = self.now_utc
            res = process_expiration(is_live=True)

        self.assertEqual(res["status"], "SUCCESS")
        self.assertEqual(res["updated_count"], 1)
        self.assertEqual(res["notifications_sent"], 0)
        self.assertEqual(res["notifications_failed"], 1)

        # Database update remains committed and successful
        d101 = self.TestSession.get(Donation, 101)
        self.assertEqual(d101.status, "EXPIRED", "DB commit must remain intact despite SNS failure")


if __name__ == "__main__":
    unittest.main()
