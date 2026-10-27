"""
FoodBridge Automated Donation Expiration Trigger
AWS Lambda Function: foodbridge-expiry-scheduler
Target EC2 Instance: i-01d9b606fb86b2dbd

Dispatches a secure SSM Run Command (AWS-RunShellScript) to EC2 instance i-01d9b606fb86b2dbd.
Executes the standalone expiry script in DRY-RUN mode.
Polls for execution completion and returns structured audit results to CloudWatch Logs.

Security:
- Zero public administrative endpoints exposed
- Fully authenticated via AWS SigV4
- Zero database credentials, tokens, or personal data logged
"""

import json
import logging
import time
import boto3
from botocore.exceptions import ClientError

logger = logging.getLogger()
logger.setLevel(logging.INFO)

TARGET_INSTANCE_ID = "i-01d9b606fb86b2dbd"
SSM_DOCUMENT_NAME = "AWS-RunShellScript"
# Strict DRY-RUN invocation for safety
COMMAND = "sudo -u ubuntu /var/www/foodbridge/venv/bin/python3 /var/www/foodbridge/scripts/expire_donations.py --dry-run"

MAX_POLL_ATTEMPTS = 10
POLL_INTERVAL_SECONDS = 2  # Total max wait: ~20 seconds

ssm_client = boto3.client("ssm", region_name="ap-south-1")


def lambda_handler(event, context):
    logger.info(f"Initiating FoodBridge expiry run on instance {TARGET_INSTANCE_ID} (DRY-RUN mode)")

    try:
        # 1. Dispatch SSM Run Command strictly to the approved instance
        send_resp = ssm_client.send_command(
            InstanceIds=[TARGET_INSTANCE_ID],
            DocumentName=SSM_DOCUMENT_NAME,
            Parameters={"commands": [COMMAND]},
            TimeoutSeconds=30,
            Comment="FoodBridge Scheduled Donation Expiration (DRY-RUN)",
        )

        command_id = send_resp["Command"]["CommandId"]
        logger.info(f"SSM Command dispatched successfully. CommandId: {command_id}")

        # 2. Poll for command invocation completion
        status = "Pending"
        stdout = ""
        stderr = ""
        response_code = -1

        for attempt in range(1, MAX_POLL_ATTEMPTS + 1):
            time.sleep(POLL_INTERVAL_SECONDS)
            try:
                inv = ssm_client.get_command_invocation(
                    CommandId=command_id,
                    InstanceId=TARGET_INSTANCE_ID,
                )
                status = inv.get("Status", "Unknown")
                response_code = inv.get("ResponseCode", -1)
                stdout = inv.get("StandardOutputContent", "").strip()
                stderr = inv.get("StandardErrorContent", "").strip()

                logger.info(f"Poll attempt {attempt}/{MAX_POLL_ATTEMPTS}: Status = {status}")

                if status in ["Success", "Failed", "TimedOut", "Cancelled"]:
                    break
            except ClientError as e:
                # Command invocation details might not be immediately available
                logger.warning(f"Poll attempt {attempt} encountered ClientError: {e}")

        # 3. Handle Terminal Execution Statuses
        if status == "Success":
            try:
                parsed_output = json.loads(stdout)
            except (json.JSONDecodeError, ValueError):
                parsed_output = {"raw_output": stdout}

            logger.info(f"Expiry execution SUCCEEDED on instance. Result: {json.dumps(parsed_output)}")
            return {
                "statusCode": 200,
                "status": "SUCCESS",
                "command_id": command_id,
                "instance_id": TARGET_INSTANCE_ID,
                "execution_result": parsed_output,
            }

        elif status in ["Pending", "InProgress", "Delayed"]:
            # Command still running; do not falsely claim failure or success
            logger.warning(f"Command {command_id} did not finish within {MAX_POLL_ATTEMPTS * POLL_INTERVAL_SECONDS}s. Status: {status}")
            return {
                "statusCode": 202,
                "status": "PENDING",
                "command_id": command_id,
                "instance_id": TARGET_INSTANCE_ID,
                "message": f"Command was accepted and is currently {status} on EC2. Check Systems Manager Run Command history.",
            }

        else:
            # Command failed, timed out, or was cancelled
            logger.error(f"Expiry execution FAILED with status: {status}. ExitCode: {response_code}. Stderr: {stderr}")
            return {
                "statusCode": 500,
                "status": "FAILED",
                "command_id": command_id,
                "instance_id": TARGET_INSTANCE_ID,
                "exit_code": response_code,
                "error_status": status,
                "stderr": stderr,
                "stdout": stdout,
            }

    except ClientError as e:
        logger.error(f"AWS SSM API ClientError: {e}")
        return {
            "statusCode": 500,
            "status": "ERROR",
            "error_type": "ClientError",
            "message": str(e),
        }
    except Exception as e:
        logger.error(f"Unhandled exception during Lambda execution: {type(e).__name__} - {e}")
        return {
            "statusCode": 500,
            "status": "ERROR",
            "error_type": type(e).__name__,
            "message": str(e),
        }
