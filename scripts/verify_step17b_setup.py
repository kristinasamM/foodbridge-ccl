import os
import sys
import json
import urllib.request
import urllib.error
import boto3
from botocore.exceptions import ClientError

BUCKET_NAME = "foodbridge-donations-879385476807-v2"
REGION = "ap-south-1"
TEST_KEY = "donations/.step17b_setup_probe.txt"
NON_DONATION_KEY = "other_prefix/forbidden_probe.txt"

print("==================================================")
print("TASK 1: Setup Verification & Access Checks")
print("==================================================")

# 1. AWS Account & IAM Role check via STS
print("\n[CHECK 1] Confirming AWS Account & IAM Role...")
try:
    sts = boto3.client("sts", region_name=REGION)
    caller = sts.get_caller_identity()
    account_id = caller.get("Account")
    arn = caller.get("Arn")
    role_id = caller.get("UserId")
    print(f"  Account ID: {account_id}")
    print(f"  Caller ARN: {arn}")
    print(f"  Role / User ID: {role_id}")
    if account_id == "879385476807":
        print("  [PASS] AWS Account ID confirmed: 879385476807")
    else:
        print(f"  [FAIL] Unexpected AWS Account ID: {account_id}")
    if "FoodBridge-EC2-App-Role" in arn:
        print("  [PASS] EC2 IAM Role confirmed: FoodBridge-EC2-App-Role")
    else:
        print(f"  [WARN] Caller ARN does not contain expected role name: {arn}")
except Exception as e:
    print(f"  [FAIL] STS GetCallerIdentity failed: {e}")

# 2. Confirm Bucket Exists in ap-south-1 via HTTP endpoint
print(f"\n[CHECK 2] Confirming bucket '{BUCKET_NAME}' region...")
bucket_url = f"https://{BUCKET_NAME}.s3.{REGION}.amazonaws.com/"
try:
    req = urllib.request.Request(bucket_url, method="HEAD")
    resp = urllib.request.urlopen(req)
    print(f"  Bucket HTTP response: {resp.status}")
except urllib.error.HTTPError as e:
    headers = dict(e.headers)
    bucket_region = headers.get("x-amz-bucket-region", "unknown")
    server = headers.get("Server", "unknown")
    print(f"  Bucket HTTP Status: {e.code} ({e.reason})")
    print(f"  S3 Server Header: {server}")
    print(f"  x-amz-bucket-region: {bucket_region}")
    if bucket_region == REGION or (e.code == 403 and server == "AmazonS3"):
        print(f"  [PASS] Bucket exists in region '{REGION}'")
    else:
        print(f"  [FAIL] Bucket region mismatch or unexpected response: {bucket_region}")
except Exception as e:
    print(f"  [FAIL] Connection error: {e}")

# 3 & 4. Verify EC2 role access on donations/ and SSE-S3 encryption
print(f"\n[CHECK 3 & 4] Testing EC2 Role S3 Permissions & SSE-S3 Encryption...")
s3 = boto3.client("s3", region_name=REGION)

# Test PutObject on donations/
probe_payload = b"Step 17B Setup Verification Probe - FoodBridge"
put_success = False
try:
    put_resp = s3.put_object(
        Bucket=BUCKET_NAME,
        Key=TEST_KEY,
        Body=probe_payload,
        ContentType="text/plain",
        ServerSideEncryption="AES256"
    )
    sse = put_resp.get("ServerSideEncryption", "Unknown")
    print(f"  [PASS] s3:PutObject to '{TEST_KEY}' SUCCEEDED.")
    print(f"  [PASS] ServerSideEncryption: {sse}")
    put_success = True
except ClientError as e:
    print(f"  [FAIL] s3:PutObject failed: {e}")

# Test GetObject on donations/
if put_success:
    try:
        get_resp = s3.get_object(Bucket=BUCKET_NAME, Key=TEST_KEY)
        downloaded = get_resp["Body"].read()
        sse_get = get_resp.get("ServerSideEncryption", "None")
        content_type = get_resp.get("ContentType")
        print(f"  [PASS] s3:GetObject from '{TEST_KEY}' SUCCEEDED.")
        print(f"  Payload matches: {downloaded == probe_payload}")
        print(f"  Content-Type: {content_type}")
        print(f"  ServerSideEncryption (GetObject): {sse_get}")
        if sse_get == "AES256":
            print("  [PASS] SSE-S3 (AES256) Encryption verified.")
        else:
            print(f"  [WARN] Unexpected encryption header: {sse_get}")
    except ClientError as e:
        print(f"  [FAIL] s3:GetObject failed: {e}")

# Test Least-Privilege Scoping: Non-donations prefix should fail
print(f"\n[CHECK 4b] Testing Scoped Access Restriction (Negative Test)...")
try:
    s3.put_object(
        Bucket=BUCKET_NAME,
        Key=NON_DONATION_KEY,
        Body=b"Should be denied",
        ServerSideEncryption="AES256"
    )
    print("  [WARN] PutObject to non-donations prefix was ALLOWED (policy not strictly scoped).")
except ClientError as e:
    err_code = e.response.get("Error", {}).get("Code")
    if err_code == "AccessDenied":
        print(f"  [PASS] Access denied outside 'donations/*' as expected ({err_code}). Scoping is verified!")
    else:
        print(f"  [INFO] Negative test returned: {err_code}")

# Block Public Access test
print(f"\n[CHECK 3b] Verifying Block Public Access (Unauthenticated GET)...")
unauth_url = f"https://{BUCKET_NAME}.s3.{REGION}.amazonaws.com/{TEST_KEY}"
try:
    req = urllib.request.Request(unauth_url, method="GET")
    with urllib.request.urlopen(req) as resp:
        print(f"  [WARNING] Unauthenticated GET SUCCEEDED with HTTP {resp.status}! Bucket is PUBLIC!")
except urllib.error.HTTPError as e:
    if e.code == 403:
        print(f"  [PASS] Unauthenticated GET returned HTTP 403 Forbidden ({e.reason}). Public access is blocked.")
    else:
        print(f"  [INFO] Unauthenticated GET returned HTTP {e.code}: {e.reason}")
except Exception as e:
    print(f"  [INFO] Unauthenticated GET error: {e}")

# 5. Website HTTP 200 and MySQL Connectivity
print("\n[CHECK 5] Verifying Website HTTP 200 and MySQL Connectivity...")
try:
    req = urllib.request.Request("http://127.0.0.1/", headers={"Host": "localhost"})
    with urllib.request.urlopen(req, timeout=5) as resp:
        print(f"  [PASS] Website returned HTTP Status: {resp.status} ({resp.reason})")
except Exception as e:
    print(f"  [FAIL] Local HTTP request failed: {e}")

# MySQL Connectivity & Record Counts
os.environ["USE_SECRETS_MANAGER"] = "true"
os.environ["RDS_SECRET_NAME"] = "foodbridge/app-db-credentials"
os.environ["AWS_REGION"] = REGION
sys.path.insert(0, "/var/www/foodbridge")

try:
    from app import app, db, User, Donation, Reservation
    with app.app_context():
        engine_name = db.engine.name
        print(f"  [PASS] Active Database Engine: {engine_name}")
        assert engine_name == "mysql", f"Expected 'mysql', got '{engine_name}'"
        
        users_count = User.query.count()
        donations_count = Donation.query.count()
        reservations_count = Reservation.query.count()
        
        print(f"  Database Counts:")
        print(f"    Users:        {users_count} (Expected: 7)")
        print(f"    Donations:    {donations_count} (Expected: 4)")
        print(f"    Reservations: {reservations_count} (Expected: 1)")
        
        if users_count == 7 and donations_count == 4 and reservations_count == 1:
            print("  [PASS] All expected records intact (7 users, 4 donations, 1 reservation).")
        else:
            print(f"  [WARN] Record count discrepancy! Users={users_count}, Donations={donations_count}, Res={reservations_count}")
except Exception as e:
    print(f"  [FAIL] MySQL verification failed: {e}")

print("\n==================================================")
print("TASK 1 Verification Complete")
print("==================================================")
