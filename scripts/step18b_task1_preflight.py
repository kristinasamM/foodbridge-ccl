import os
import sys
import subprocess
import urllib.request
import boto3
from botocore.exceptions import ClientError

REGION = "ap-south-1"
EXPECTED_ACCOUNT = "879385476807"
TOPIC_ARN = f"arn:aws:sns:{REGION}:{EXPECTED_ACCOUNT}:foodbridge-notifications"
EC2_IP = "13.206.208.91"
BACKUP_DIR = "/home/ubuntu/backups"

print("==================================================")
print("TASK 1: Step 18B Pre-Deployment Safety Checks")
print("==================================================")

# 1. Account & Region
print("\n[CHECK 1] Confirming AWS Account & Region...")
sts = boto3.client("sts", region_name=REGION)
caller = sts.get_caller_identity()
account_id = caller.get("Account")
arn = caller.get("Arn")
print(f"  Account ID: {account_id}")
print(f"  Caller ARN: {arn}")
assert account_id == EXPECTED_ACCOUNT, f"Expected {EXPECTED_ACCOUNT}, got {account_id}"
assert "FoodBridge-EC2-App-Role" in arn, f"Expected role FoodBridge-EC2-App-Role, got {arn}"
print("  [PASS] AWS Account and EC2 IAM Role verified.")

# 2. Website HTTP 200
print("\n[CHECK 2] Confirming Website HTTP 200...")
req = urllib.request.Request("http://127.0.0.1/", headers={"Host": EC2_IP})
with urllib.request.urlopen(req, timeout=5) as resp:
    print(f"  Public website HTTP: {resp.status} ({resp.reason})")
    assert resp.status == 200, f"Expected 200, got {resp.status}"
print("  [PASS] Website returns HTTP 200 OK.")

# 3. Gunicorn and Nginx Status
print("\n[CHECK 3] Checking Gunicorn and Nginx...")
for svc in ["foodbridge.service", "nginx"]:
    out = subprocess.check_output(["sudo", "systemctl", "is-active", svc]).decode("utf-8").strip()
    print(f"  {svc}: {out}")
    assert out == "active", f"{svc} is not active: {out}"
print("  [PASS] Services are healthy and active.")

# 4. Production Database Engine & S3 Integration
print("\n[CHECK 4] Checking MySQL Engine and S3 Integration...")
env_file = "/var/www/foodbridge/.env"
with open(env_file, "r") as f:
    env_content = f.read()
assert "USE_SECRETS_MANAGER=true" in env_content, "USE_SECRETS_MANAGER missing"
assert "USE_S3=true" in env_content, "USE_S3 missing"
print("  [PASS] .env has USE_SECRETS_MANAGER=true and USE_S3=true.")

os.environ["USE_SECRETS_MANAGER"] = "true"
os.environ["RDS_SECRET_NAME"] = "foodbridge/app-db-credentials"
os.environ["AWS_REGION"] = REGION
os.environ["USE_S3"] = "true"
sys.path.insert(0, "/var/www/foodbridge")

from app import app, db, User, Donation, Reservation
with app.app_context():
    engine_name = db.engine.name
    print(f"  Active Database Engine: {engine_name}")
    assert engine_name == "mysql", f"Expected mysql, got {engine_name}"
    u_cnt = User.query.count()
    d_cnt = Donation.query.count()
    r_cnt = Reservation.query.count()
    print(f"  Current DB Counts: Users={u_cnt}, Donations={d_cnt}, Reservations={r_cnt}")
    assert u_cnt == 7 and d_cnt == 4 and r_cnt == 1, "Discrepancy in existing database counts!"
print("  [PASS] Production database engine is MySQL with intact record counts.")

# 5. Existing Backups Intact
print("\n[CHECK 5] Confirming Existing Backups...")
assert os.path.exists(BACKUP_DIR), f"{BACKUP_DIR} not found"
backups = sorted(os.listdir(BACKUP_DIR))
print(f"  Found {len(backups)} backup folders:")
for b in backups:
    print(f"    - {b}")
assert len(backups) >= 4, f"Expected at least 4 backup folders, found {len(backups)}"
print("  [PASS] Existing backups intact.")

# 6. Verify SNS Topic Exists and EC2 Role Can Publish (Dry run / probe)
print("\n[CHECK 6] Verifying SNS Topic and EC2 Role Publish Permission...")
sns = boto3.client("sns", region_name=REGION)
try:
    # We do a test publish with a clearly labeled harmless message as specified in Task 7
    # "Keep the test subject clearly identifiable: [FoodBridge TEST] SNS Integration Verification"
    resp = sns.publish(
        TopicArn=TOPIC_ARN,
        Subject="[FoodBridge TEST] SNS Integration Verification",
        Message=(
            "FoodBridge AWS Mini-Project - Step 18B\n\n"
            "This is a pre-deployment verification message confirming that the EC2 IAM Role "
            "(FoodBridge-EC2-App-Role) has active permission to publish to the FoodBridge SNS Topic.\n\n"
            "Timestamp: " + str(os.popen("date -u").read().strip()) + "\n"
            "Instance ID: i-01d9b606fb86b2dbd\n"
            "Status: Verified\n"
        ),
        MessageAttributes={
            "event_type": {"DataType": "String", "StringValue": "TEST_VERIFICATION"}
        }
    )
    msg_id = resp.get("MessageId")
    print(f"  [PASS] sns:Publish to {TOPIC_ARN} SUCCEEDED!")
    print(f"  MessageId: {msg_id}")
    print(f"  HTTP StatusCode: {resp.get('ResponseMetadata', {}).get('HTTPStatusCode')}")
except ClientError as e:
    err_code = e.response.get("Error", {}).get("Code")
    err_msg = e.response.get("Error", {}).get("Message")
    print(f"  [FAIL] sns:Publish failed: {err_code} - {err_msg}")
    sys.exit(1)

print("\n==================================================")
print("TASK 1 Pre-Deployment Safety Checks: ALL PASSED")
print("==================================================")
