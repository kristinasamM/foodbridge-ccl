#!/usr/bin/env python3
"""
Step 18B SNS Publish Verification Script
Runs on EC2 using IAM Role FoodBridge-EC2-App-Role.
Publishes one clearly labeled, harmless SNS test notification to the FoodBridge SNS topic.
Does NOT create or modify any database records.
"""
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, "/var/www/foodbridge")

env_file = "/var/www/foodbridge/.env"
if os.path.exists(env_file):
    with open(env_file, "r") as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ[k.strip()] = v.strip()

from app import app, get_sns_client

def main():
    print("=" * 60)
    print("FOODBRIDGE STEP 18B LIVE SNS VERIFICATION")
    print("=" * 60)

    topic_arn = os.environ.get("SNS_TOPIC_ARN", "arn:aws:sns:ap-south-1:879385476807:foodbridge-notifications")
    subject = "[FoodBridge TEST] SNS Integration Verification"
    timestamp_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")

    body = f"""Hello,

This is a test notification from the FoodBridge web application running on Amazon EC2 (Instance: i-01d9b606fb86b2dbd) in AWS Region ap-south-1.

Verification Details:
- Application: FoodBridge (Step 18B Verification)
- Sender IAM Role: FoodBridge-EC2-App-Role
- Topic ARN: {topic_arn}
- Timestamp: {timestamp_str}
- Integration Status: Amazon SNS Integration Verified Successfully

No action is required. This test confirmed that the EC2 instance role can publish application notifications to the FoodBridge SNS topic.
"""

    print(f"Target Topic ARN: {topic_arn}")
    print(f"Subject: {subject}")
    print("\nPublishing single test message via EC2 IAM Role...")

    client = get_sns_client()
    resp = client.publish(
        TopicArn=topic_arn,
        Subject=subject,
        Message=body,
        MessageAttributes={
            "event_type": {
                "DataType": "String",
                "StringValue": "TEST_VERIFICATION",
            }
        },
    )

    message_id = resp.get("MessageId")
    http_status = resp.get("ResponseMetadata", {}).get("HTTPStatusCode")

    print("\nPublish Result:")
    print(f"  HTTP Status Code: {http_status}")
    print(f"  MessageId: {message_id}")

    if http_status == 200 and message_id:
        print("\nSUCCESS: Verification notification successfully published to Amazon SNS.")
    else:
        print(f"\nFAILURE: Unexpected response: {resp}")
        sys.exit(1)

if __name__ == "__main__":
    main()
