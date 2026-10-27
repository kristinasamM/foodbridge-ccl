import os
import sys
import hashlib
import urllib.request
import urllib.error
import boto3
from botocore.exceptions import ClientError

BUCKET_NAME = "foodbridge-donations-879385476807-v2"
REGION = "ap-south-1"
UPLOADS_DIR = "/var/www/foodbridge/static/uploads"
BACKUPS_DIR = "/home/ubuntu/backups"
EC2_IP = "13.206.208.91"

print("==================================================")
print("STEP 17C: TASK 1 — Pre-Deployment Checks")
print("==================================================")

# 1. AWS Account & Region
print("\n[CHECK 1] Verifying AWS Account & EC2 IAM Role...")
sts = boto3.client("sts", region_name=REGION)
caller = sts.get_caller_identity()
account_id = caller.get("Account")
arn = caller.get("Arn")
print(f"  Account ID: {account_id}")
print(f"  Caller ARN: {arn}")
assert account_id == "879385476807", f"Expected account 879385476807, got {account_id}"
assert "FoodBridge-EC2-App-Role" in arn, f"Expected role FoodBridge-EC2-App-Role, got {arn}"
print("  [PASS] AWS Account and IAM Role verified.")

# 2. Website HTTP 200
print("\n[CHECK 2] Verifying Website Public HTTP 200...")
req = urllib.request.Request("http://127.0.0.1/", headers={"Host": EC2_IP})
with urllib.request.urlopen(req, timeout=5) as resp:
    print(f"  Root endpoint status: {resp.status} ({resp.reason})")
    assert resp.status == 200, f"Expected 200, got {resp.status}"
print("  [PASS] Website returns HTTP 200.")

# 3 & 4. MySQL Connection & Database Records
print("\n[CHECK 3 & 4] Verifying MySQL Connection & Records...")
os.environ["USE_SECRETS_MANAGER"] = "true"
os.environ["RDS_SECRET_NAME"] = "foodbridge/app-db-credentials"
os.environ["AWS_REGION"] = REGION
sys.path.insert(0, "/var/www/foodbridge")

from app import app, db, User, Donation, Reservation

with app.app_context():
    engine_name = db.engine.name
    print(f"  Active Database Engine: {engine_name}")
    assert engine_name == "mysql", f"Expected mysql, got {engine_name}"

    users = User.query.order_by(User.id).all()
    print(f"  Users: {len(users)} (Expected: 7)")
    assert len(users) == 7, f"Expected 7 users, got {len(users)}"

    donations = Donation.query.order_by(Donation.id).all()
    print(f"  Donations: {len(donations)} (Expected: 4)")
    assert len(donations) == 4, f"Expected 4 donations, got {len(donations)}"
    for d in donations:
        print(f"    - Donation #{d.id}: '{d.food_name}' | Image: {d.image_filename} | Status: {d.status}")

    reservations = Reservation.query.order_by(Reservation.id).all()
    print(f"  Reservations: {len(reservations)} (Expected: 1)")
    assert len(reservations) == 1, f"Expected 1 reservation, got {len(reservations)}"

# 5. Verify the 3 S3 Objects and Checksums
print("\n[CHECK 5] Verifying 3 S3 Objects and Checksums...")
s3 = boto3.client("s3", region_name=REGION)
expected_files = [
    "08cb4dd54e_71JISmXA8LL._AC_UF8941000_QL80_.jpg",
    "293f808e06_71JISmXA8LL._AC_UF8941000_QL80_.jpg",
    "b6d4a88c66_71JISmXA8LL._AC_UF8941000_QL80_.jpg"
]
expected_sha256 = "099599280da80899ee595039be164cce2209438bb98733d3c2b7b4479f121250"

for fname in expected_files:
    s3_key = f"donations/{fname}"
    resp = s3.get_object(Bucket=BUCKET_NAME, Key=s3_key)
    body = resp["Body"].read()
    s3_sha256 = hashlib.sha256(body).hexdigest()
    s3_size = len(body)
    s3_ct = resp.get("ContentType")
    s3_sse = resp.get("ServerSideEncryption")
    print(f"  S3 Key: {s3_key}")
    print(f"    Size: {s3_size} B | Content-Type: {s3_ct} | SSE: {s3_sse}")
    print(f"    SHA256: {s3_sha256}")
    assert s3_sha256 == expected_sha256, f"Checksum mismatch for {s3_key}"
    assert s3_size == 65772, f"Size mismatch for {s3_key}"
    assert s3_ct == "image/jpeg", f"ContentType mismatch for {s3_key}"
    assert s3_sse == "AES256", f"SSE mismatch for {s3_key}"
print("  [PASS] All 3 S3 objects verified with matching SHA-256 and AES256 encryption.")

# 6. Verify EC2 IAM Role Permissions (s3:PutObject and s3:GetObject)
print("\n[CHECK 6] Verifying EC2 IAM Role s3:PutObject & s3:GetObject Permissions...")
probe_key = "donations/.step17c_preflight_probe.txt"
s3.put_object(
    Bucket=BUCKET_NAME,
    Key=probe_key,
    Body=b"Step 17C Preflight Probe",
    ContentType="text/plain",
    ServerSideEncryption="AES256"
)
probe_resp = s3.get_object(Bucket=BUCKET_NAME, Key=probe_key)
probe_content = probe_resp["Body"].read()
assert probe_content == b"Step 17C Preflight Probe", "Probe content mismatch"
print("  [PASS] s3:PutObject and s3:GetObject confirmed functional.")

# 7. Verify Backups on EC2
print("\n[CHECK 7] Verifying Existing Backups on EC2...")
assert os.path.exists(BACKUPS_DIR), f"Backup dir {BACKUPS_DIR} not found"
backups = sorted(os.listdir(BACKUPS_DIR))
print(f"  Found {len(backups)} backup directories: {backups}")
assert len(backups) >= 2, "Expected at least 2 backup folders"
print("  [PASS] Backups verified intact.")

print("\n==================================================")
print("TASK 1 Pre-Deployment Checks: ALL PASSED")
print("==================================================")
