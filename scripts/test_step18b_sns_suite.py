import os
import sys
import unittest
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch
from botocore.exceptions import ClientError, ConnectTimeoutError

# Project root in path
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, PROJECT_ROOT)

import app
from app import (
    app as flask_app,
    db,
    User,
    Donation,
    Reservation,
    build_sns_message,
    publish_sns_notification,
    SUPPORTED_SNS_EVENTS,
)
from flask_sqlalchemy.query import Query


class Step18BSNSTestSuite(unittest.TestCase):
    def setUp(self):
        flask_app.config["TESTING"] = True
        flask_app.config["WTF_CSRF_ENABLED"] = False
        self.client = flask_app.test_client()
        self.expected_topic_arn = "arn:aws:sns:ap-south-1:879385476807:foodbridge-notifications"

        # Mock dummy donation model for unit testing
        self.dummy_donation = Donation(
            id=101,
            donor_id=2,
            food_name="Fresh Sandwiches & Wraps",
            category="Cooked Food",
            quantity=20,
            pickup_location="Andheri West Community Hall",
            available_until=datetime(2026, 12, 31, 20, 0, tzinfo=timezone.utc),
            description="Assorted veg wraps packed hygienically",
            status="AVAILABLE",
        )

    # --------------------------------------------------------------------------
    # 1 & 2 & 4. Message Formatting for all 4 Event Types (Sanitized, No Secrets)
    # --------------------------------------------------------------------------
    def test_build_sns_message_created(self):
        subject, body = build_sns_message("DONATION_CREATED", donation=self.dummy_donation)
        self.assertEqual(subject, "[FoodBridge] New Donation Available: Fresh Sandwiches & Wraps")
        self.assertIn("Fresh Sandwiches & Wraps", body)
        self.assertIn("#101", body)
        self.assertIn("20 servings/units", body)
        self.assertIn("Andheri West Community Hall", body)
        # Verify no sensitive data
        self.assertNotIn("password", body.lower())
        self.assertNotIn("hash", body.lower())
        self.assertNotIn("secret", body.lower())

    def test_build_sns_message_reserved(self):
        subject, body = build_sns_message(
            "DONATION_RESERVED", donation=self.dummy_donation, ngo_name="Care Foundation"
        )
        self.assertEqual(subject, "[FoodBridge] Donation Reserved: Fresh Sandwiches & Wraps")
        self.assertIn("Care Foundation", body)
        self.assertIn("RESERVED", body)
        self.assertNotIn("password", body.lower())

    def test_build_sns_message_collected(self):
        subject, body = build_sns_message("DONATION_COLLECTED", donation=self.dummy_donation)
        self.assertEqual(subject, "[FoodBridge] Donation Collected: Fresh Sandwiches & Wraps")
        self.assertIn("COMPLETED", body)
        self.assertNotIn("password", body.lower())

    def test_build_sns_message_expired(self):
        subject, body = build_sns_message("DONATION_EXPIRED", donation=self.dummy_donation)
        self.assertEqual(subject, "[FoodBridge] Donation Expired: Fresh Sandwiches & Wraps")
        self.assertIn("EXPIRED", body)
        self.assertNotIn("password", body.lower())

    def test_build_sns_message_invalid_event(self):
        with self.assertRaises(ValueError):
            build_sns_message("UNKNOWN_EVENT", donation=self.dummy_donation)

    # --------------------------------------------------------------------------
    # 3 & 5. Successful SNS Publishing to Correct Topic ARN
    # --------------------------------------------------------------------------
    def test_successful_sns_publishing(self):
        mock_sns = MagicMock()
        mock_sns.publish.return_value = {
            "MessageId": "mock-msg-uuid-12345",
            "ResponseMetadata": {"HTTPStatusCode": 200},
        }

        with patch("app.get_sns_client", return_value=mock_sns):
            with patch.dict(flask_app.config, {"USE_SNS": True, "SNS_TOPIC_ARN": self.expected_topic_arn}):
                success, msg_id = publish_sns_notification(
                    "DONATION_CREATED", donation=self.dummy_donation
                )
                self.assertTrue(success)
                self.assertEqual(msg_id, "mock-msg-uuid-12345")

                # Verify publish parameters
                mock_sns.publish.assert_called_once()
                call_args = mock_sns.publish.call_args[1]
                self.assertEqual(call_args["TopicArn"], self.expected_topic_arn)
                self.assertEqual(call_args["Subject"], "[FoodBridge] New Donation Available: Fresh Sandwiches & Wraps")
                self.assertEqual(call_args["MessageAttributes"]["event_type"]["StringValue"], "DONATION_CREATED")

    # --------------------------------------------------------------------------
    # 6. SNS Permission Failure (Non-blocking, Handled Gracefully)
    # --------------------------------------------------------------------------
    def test_sns_permission_failure_handled_gracefully(self):
        mock_sns = MagicMock()
        mock_sns.publish.side_effect = ClientError(
            {"Error": {"Code": "AuthorizationError", "Message": "Not authorized to publish"}},
            "Publish",
        )

        with patch("app.get_sns_client", return_value=mock_sns):
            with patch.dict(flask_app.config, {"USE_SNS": True, "SNS_TOPIC_ARN": self.expected_topic_arn}):
                success, msg_id = publish_sns_notification(
                    "DONATION_CREATED", donation=self.dummy_donation
                )
                self.assertFalse(success)
                self.assertIsNone(msg_id)

    # --------------------------------------------------------------------------
    # 7. SNS Network Timeout (Non-blocking, Handled Gracefully)
    # --------------------------------------------------------------------------
    def test_sns_timeout_handled_gracefully(self):
        mock_sns = MagicMock()
        mock_sns.publish.side_effect = ConnectTimeoutError(endpoint_url="https://sns.ap-south-1.amazonaws.com")

        with patch("app.get_sns_client", return_value=mock_sns):
            with patch.dict(flask_app.config, {"USE_SNS": True, "SNS_TOPIC_ARN": self.expected_topic_arn}):
                success, msg_id = publish_sns_notification(
                    "DONATION_CREATED", donation=self.dummy_donation
                )
                self.assertFalse(success)
                self.assertIsNone(msg_id)

    # --------------------------------------------------------------------------
    # 8. Database Commit Failure Must NOT Publish SNS Message
    # --------------------------------------------------------------------------
    def test_db_commit_failure_prevents_sns_publish(self):
        mock_sns = MagicMock()

        with patch("app.get_sns_client", return_value=mock_sns):
            with patch.dict(flask_app.config, {"USE_SNS": True}):
                with self.client.session_transaction() as sess:
                    sess["user_id"] = 2
                    sess["user_role"] = "donor"
                    sess["user_name"] = "Donor Joe"

                data = {
                    "food_name": "Test DB Error Food",
                    "category": "Cooked Food",
                    "quantity": "10",
                    "pickup_location": "Kitchen Hub",
                    "available_until": "2026-12-31T23:59",
                    "description": "Will simulate DB failure",
                }

                # Simulate database commit failure
                with patch.object(db.session, "commit", side_effect=RuntimeError("DB Connection Lost")):
                    with self.assertRaises(RuntimeError):
                        self.client.post("/donor/donations/add", data=data)

                    # Verify SNS publish was NEVER called
                    mock_sns.publish.assert_not_called()

    # --------------------------------------------------------------------------
    # 9. No Duplicate Notification on Invalid Repeated State Transitions
    # --------------------------------------------------------------------------
    def test_no_duplicate_notification_on_repeated_reserve(self):
        mock_sns = MagicMock()
        mock_donation = MagicMock()
        mock_donation.status = "RESERVED"  # Already reserved!
        mock_donation.id = 101

        with patch("app.get_sns_client", return_value=mock_sns):
            with patch.dict(flask_app.config, {"USE_SNS": True}):
                with self.client.session_transaction() as sess:
                    sess["user_id"] = 3
                    sess["user_role"] = "ngo"
                    sess["user_name"] = "Care NGO"

                with patch("app.check_and_update_expired_donations"):
                    with patch.object(Query, "get_or_404", return_value=mock_donation):
                        resp = self.client.post("/ngo/donations/101/reserve")
                        # Must redirect back with error flash
                        self.assertEqual(resp.status_code, 302)
                        # Must NOT have published SNS notification
                        mock_sns.publish.assert_not_called()

    def test_no_duplicate_notification_on_repeated_complete(self):
        mock_sns = MagicMock()
        mock_res = MagicMock()
        mock_res.ngo_id = 3
        mock_res.pickup_status = "COMPLETED"  # Already completed!

        with patch("app.get_sns_client", return_value=mock_sns):
            with patch.dict(flask_app.config, {"USE_SNS": True}):
                with self.client.session_transaction() as sess:
                    sess["user_id"] = 3
                    sess["user_role"] = "ngo"
                    sess["user_name"] = "Care NGO"

                with patch.object(Query, "get_or_404", return_value=mock_res):
                    resp = self.client.post("/ngo/reservations/1/complete")
                    self.assertEqual(resp.status_code, 302)
                    mock_sns.publish.assert_not_called()

    # --------------------------------------------------------------------------
    # 10. Development Mode (USE_SNS=false) Does NOT Publish
    # --------------------------------------------------------------------------
    def test_use_sns_false_does_not_publish(self):
        mock_sns = MagicMock()
        with patch("app.get_sns_client", return_value=mock_sns):
            with patch.dict(flask_app.config, {"USE_SNS": False}):
                success, msg_id = publish_sns_notification(
                    "DONATION_CREATED", donation=self.dummy_donation
                )
                self.assertFalse(success)
                self.assertIsNone(msg_id)
                mock_sns.publish.assert_not_called()

    # --------------------------------------------------------------------------
    # 11. Secrets Manager and S3 Configurations Remain Preserved
    # --------------------------------------------------------------------------
    def test_s3_and_secrets_manager_config_intact(self):
        self.assertIn("USE_S3", flask_app.config)
        self.assertIn("S3_BUCKET", flask_app.config)
        self.assertIn("USE_SNS", flask_app.config)
        self.assertIn("SNS_TOPIC_ARN", flask_app.config)


if __name__ == "__main__":
    unittest.main()
