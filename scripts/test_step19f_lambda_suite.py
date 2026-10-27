#!/usr/bin/env python3
"""
Unit test suite for FoodBridge Lambda SSM Trigger
File: test_step19f_lambda_suite.py
"""

import json
import os
import sys
import unittest
from unittest.mock import MagicMock, patch
from botocore.exceptions import ClientError

# Add lambda directory to sys.path
PROJECT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
LAMBDA_DIR = os.path.join(PROJECT_DIR, "infrastructure", "lambda")
sys.path.insert(0, LAMBDA_DIR)

import lambda_function


class Step19FLambdaTestSuite(unittest.TestCase):
    def setUp(self):
        self.mock_ssm = MagicMock()
        lambda_function.ssm_client = self.mock_ssm

    def test_send_command_parameters(self):
        # Mock send_command and immediate success
        self.mock_ssm.send_command.return_value = {
            "Command": {"CommandId": "mock-cmd-12345"}
        }
        self.mock_ssm.get_command_invocation.return_value = {
            "Status": "Success",
            "ResponseCode": 0,
            "StandardOutputContent": json.dumps({
                "status": "SUCCESS",
                "mode": "DRY_RUN",
                "eligible_count": 2,
                "eligible_donations": [{"id": 3}, {"id": 4}],
                "database_updated": False,
            }),
            "StandardErrorContent": "",
        }

        with patch("time.sleep", return_value=None):
            resp = lambda_function.lambda_handler({}, None)

        self.assertEqual(resp["statusCode"], 200)
        self.assertEqual(resp["status"], "SUCCESS")
        self.assertEqual(resp["command_id"], "mock-cmd-12345")
        self.assertEqual(resp["execution_result"]["eligible_count"], 2)

        # Verify send_command call parameters
        self.mock_ssm.send_command.assert_called_once()
        call_kwargs = self.mock_ssm.send_command.call_args[1]
        self.assertEqual(call_kwargs["InstanceIds"], ["i-01d9b606fb86b2dbd"])
        self.assertEqual(call_kwargs["DocumentName"], "AWS-RunShellScript")
        self.assertIn("--live", call_kwargs["Parameters"]["commands"][0])
        self.assertNotIn("--dry-run", call_kwargs["Parameters"]["commands"][0])

    def test_ssm_command_failure_handled(self):
        self.mock_ssm.send_command.return_value = {
            "Command": {"CommandId": "mock-cmd-fail"}
        }
        self.mock_ssm.get_command_invocation.return_value = {
            "Status": "Failed",
            "ResponseCode": 1,
            "StandardOutputContent": "",
            "StandardErrorContent": "OperationalError: connection lost",
        }

        with patch("time.sleep", return_value=None):
            resp = lambda_function.lambda_handler({}, None)

        self.assertEqual(resp["statusCode"], 500)
        self.assertEqual(resp["status"], "FAILED")
        self.assertEqual(resp["exit_code"], 1)
        self.assertIn("OperationalError", resp["stderr"])

    def test_ssm_command_pending_timeout_handled(self):
        self.mock_ssm.send_command.return_value = {
            "Command": {"CommandId": "mock-cmd-slow"}
        }
        self.mock_ssm.get_command_invocation.return_value = {
            "Status": "InProgress",
            "ResponseCode": -1,
            "StandardOutputContent": "",
            "StandardErrorContent": "",
        }

        with patch("time.sleep", return_value=None):
            resp = lambda_function.lambda_handler({}, None)

        self.assertEqual(resp["statusCode"], 202)
        self.assertEqual(resp["status"], "PENDING")
        self.assertIn("inprogress", resp["message"].lower())

    def test_ssm_api_client_error(self):
        self.mock_ssm.send_command.side_effect = ClientError(
            {"Error": {"Code": "AccessDeniedException", "Message": "Not authorized to SendCommand"}},
            "SendCommand"
        )

        resp = lambda_function.lambda_handler({}, None)
        self.assertEqual(resp["statusCode"], 500)
        self.assertEqual(resp["status"], "ERROR")
        self.assertEqual(resp["error_type"], "ClientError")


if __name__ == "__main__":
    unittest.main()
