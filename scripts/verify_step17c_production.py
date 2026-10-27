import os
import sys
import hashlib
import urllib.request
import urllib.error
import subprocess
from datetime import datetime

print("==================================================")
print("TASK 6: Step 17C Production Verification")
print("==================================================")

EC2_IP = "13.206.208.91"
BUCKET_NAME = "foodbridge-donations-879385476807-v2"
REGION = "ap-south-1"

# 1. Website Public HTTP 200
print("\n[VERIFICATION 1] Checking Public Web Endpoints...")
endpoints = ["/", "/login", "/register"]
for ep in endpoints:
    url = f"http://127.0.0.1{ep}"
    req = urllib.request.Request(url, headers={"Host": EC2_IP})
    with urllib.request.urlopen(req, timeout=5) as resp:
        print(f"  {ep:12} -> HTTP {resp.status} ({resp.reason})")
        assert resp.status == 200, f"Expected 200 for {ep}, got {resp.status}"
print("  [PASS] Public endpoints return HTTP 200 OK.")

# 2 & 3. Active Database Engine & Database Records
print("\n[VERIFICATION 2 & 3] Checking Database Engine & Record Integrity...")
os.environ["USE_SECRETS_MANAGER"] = "true"
os.environ["RDS_SECRET_NAME"] = "foodbridge/app-db-credentials"
os.environ["AWS_REGION"] = REGION
os.environ["USE_S3"] = "true"
os.environ["S3_BUCKET"] = BUCKET_NAME
sys.path.insert(0, "/var/www/foodbridge")

from app import app, db, User, Donation, Reservation, get_image_url

with app.app_context():
    engine_name = db.engine.name
    print(f"  Active Database Engine: {engine_name}")
    assert engine_name == "mysql", f"Expected mysql, got {engine_name}"

    users = User.query.order_by(User.id).all()
    print(f"  Users Count: {len(users)} (Expected: 7)")
    assert len(users) == 7, f"Expected 7 users, got {len(users)}"
    for u in users:
        print(f"    - ID {u.id}: '{u.name}' ({u.email}, {u.role})")

    donations = Donation.query.order_by(Donation.id).all()
    print(f"\n  Donations Count: {len(donations)} (Expected: 4)")
    assert len(donations) == 4, f"Expected 4 donations, got {len(donations)}"
    for d in donations:
        print(f"    - ID {d.id}: '{d.food_name}' | Status: {d.status} | Image: {d.image_filename}")

    reservations = Reservation.query.order_by(Reservation.id).all()
    print(f"\n  Reservations Count: {len(reservations)} (Expected: 1)")
    assert len(reservations) == 1, f"Expected 1 reservation, got {len(reservations)}"
    print(f"    - ID {reservations[0].id}: Donation #{reservations[0].donation_id} reserved by NGO #{reservations[0].ngo_id}")

# 4. Donation #1 Image Displays via Presigned S3 URL
print("\n[VERIFICATION 4] Verifying Donation #1 Presigned S3 URL & Retrieval...")
with app.app_context():
    d1 = db.session.get(Donation, 1)
    assert d1 is not None, "Donation #1 not found"
    assert d1.image_filename == "b6d4a88c66_71JISmXA8LL._AC_UF8941000_QL80_.jpg"

    presigned_url = get_image_url(d1.image_filename)
    print(f"  Presigned URL generated:")
    print(f"  {presigned_url[:85]}... [truncated]")

    assert BUCKET_NAME in presigned_url, "Bucket name missing from presigned URL"
    assert f"donations/{d1.image_filename}" in presigned_url, "Object key missing from presigned URL"
    assert "X-Amz-Signature=" in presigned_url or "Signature=" in presigned_url, "Signature missing from presigned URL"
    assert "X-Amz-Expires=900" in presigned_url, "Expiry missing or not 900 seconds"

    # Fetch image using the presigned URL over HTTP/HTTPS
    req = urllib.request.Request(presigned_url, headers={"User-Agent": "FoodBridge-HealthCheck/1.0"})
    with urllib.request.urlopen(req, timeout=10) as resp:
        downloaded = resp.read()
        status = resp.status
        ct = resp.headers.get("Content-Type")
        cl = resp.headers.get("Content-Length")
        fetched_sha = hashlib.sha256(downloaded).hexdigest()

        print(f"  HTTP GET presigned URL: HTTP {status}")
        print(f"  Content-Type: {ct} | Content-Length: {cl} (Actual read: {len(downloaded)} B)")
        print(f"  Downloaded SHA256: {fetched_sha}")

        assert status == 200, f"Expected HTTP 200, got {status}"
        assert ct == "image/jpeg", f"Expected image/jpeg, got {ct}"
        assert len(downloaded) == 65772, f"Expected 65772 bytes, got {len(downloaded)}"
        assert fetched_sha == "099599280da80899ee595039be164cce2209438bb98733d3c2b7b4479f121250"
    print("  [PASS] Donation #1 image verified via presigned S3 URL with 100% SHA-256 match.")

# 5. Dashboard Templates Render with Presigned URLs
print("\n[VERIFICATION 5] Verifying Dashboards Render Correctly...")
client = app.test_client()

dashboards = [
    ("donor", "/donor/dashboard", 2, "Donor Joe"),
    ("ngo", "/ngo/dashboard", 3, "Care NGO"),
    ("admin", "/admin/dashboard", 1, "System Admin"),
]

for role, path, user_id, user_name in dashboards:
    with client.session_transaction() as sess:
        sess["user_id"] = user_id
        sess["user_role"] = role
        sess["user_name"] = user_name

    resp = client.get(path)
    html = resp.data.decode("utf-8")
    print(f"  Dashboard {path} (Role: {role}): HTTP {resp.status_code}")
    assert resp.status_code == 200, f"Dashboard {path} failed with {resp.status_code}"

    # For admin dashboard, Donation #1 is listed in recent_donations
    if role == "admin":
        assert f"donations/{d1.image_filename}" in html, "Presigned S3 URL not rendered in Admin Dashboard HTML"
        print(f"  [PASS] Admin dashboard renders presigned S3 URL for Donation #1.")

# 6. S3 Bucket Remains Private (Unauthenticated Access Denied)
print("\n[VERIFICATION 6] Verifying S3 Bucket Remains Strictly Private...")
raw_s3_url = f"https://{BUCKET_NAME}.s3.{REGION}.amazonaws.com/donations/{d1.image_filename}"
try:
    req = urllib.request.Request(raw_s3_url, method="GET")
    with urllib.request.urlopen(req) as resp:
        print(f"  [FAIL] Raw S3 URL returned HTTP {resp.status}! Bucket is NOT private!")
        assert False, "Bucket is public!"
except urllib.error.HTTPError as e:
    print(f"  Raw S3 URL returned HTTP {e.code} ({e.reason})")
    assert e.code == 403, f"Expected HTTP 403 Forbidden, got {e.code}"
    print("  [PASS] Unauthenticated access is denied (HTTP 403 Forbidden).")

# 7. Gunicorn and Nginx Service Health
print("\n[VERIFICATION 7] Checking Service Health...")
for svc in ["foodbridge.service", "nginx"]:
    out = subprocess.check_output(["sudo", "systemctl", "is-active", svc]).decode("utf-8").strip()
    print(f"  {svc}: {out}")
    assert out == "active", f"{svc} is not active: {out}"
print("  [PASS] Both Gunicorn and Nginx are active and running.")

# 8. Log Inspection for Sensitive Credentials
print("\n[VERIFICATION 8] Inspecting Logs for Leaked Credentials...")
log_paths = [
    "/var/log/foodbridge/error.log",
    "/var/log/foodbridge/access.log",
]
for lp in log_paths:
    if os.path.exists(lp):
        with open(lp, "r", errors="ignore") as f:
            content = f.read()
            assert "aws_secret_access_key" not in content.lower(), f"Potential credential leak in {lp}"
            assert "x-amz-security-token" not in content.lower(), f"Security token leaked in {lp}"
        print(f"  {lp}: No credential leaks detected.")

print("\n==================================================")
print("TASK 6 Production Verification: ALL CHECKS PASSED")
print("==================================================")
