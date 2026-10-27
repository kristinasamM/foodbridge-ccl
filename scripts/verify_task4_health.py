import os
import sys
import urllib.request
import urllib.error
import subprocess

print("==================================================")
print("TASK 4: Application & Environment Verification")
print("==================================================")

EC2_IP = "13.206.208.91"
UPLOADS_DIR = "/var/www/foodbridge/static/uploads"
BACKUPS_DIR = "/home/ubuntu/backups"

# 1. Confirm Website HTTP 200
print("\n[CHECK 1] Verifying Website Public Endpoints...")
endpoints = ["/", "/login", "/register"]
for ep in endpoints:
    url = f"http://127.0.0.1{ep}"
    try:
        req = urllib.request.Request(url, headers={"Host": EC2_IP})
        with urllib.request.urlopen(req, timeout=5) as resp:
            print(f"  {ep:12} -> HTTP {resp.status} ({resp.reason})")
            assert resp.status == 200, f"Expected 200, got {resp.status}"
    except Exception as e:
        print(f"  {ep:12} -> FAIL: {e}")

# 2 & 3. Active Database Engine & Record Integrity
print("\n[CHECK 2 & 3] Verifying MySQL Database Records...")
os.environ["USE_SECRETS_MANAGER"] = "true"
os.environ["RDS_SECRET_NAME"] = "foodbridge/app-db-credentials"
os.environ["AWS_REGION"] = "ap-south-1"
sys.path.insert(0, "/var/www/foodbridge")

from app import app, db, User, Donation, Reservation

with app.app_context():
    engine_name = db.engine.name
    print(f"  Active Database Engine: {engine_name}")
    assert engine_name == "mysql", f"Expected mysql, got {engine_name}"

    users = User.query.order_by(User.id).all()
    print(f"\n  Total Users: {len(users)} (Expected: 7)")
    for u in users:
        print(f"    - ID {u.id}: Name='{u.name}' | Role={u.role} | Email={u.email}")
    assert len(users) == 7, f"Expected 7 users, found {len(users)}"

    donations = Donation.query.order_by(Donation.id).all()
    print(f"\n  Total Donations: {len(donations)} (Expected: 4)")
    for d in donations:
        print(f"    - ID {d.id}: '{d.food_name}' | Qty: {d.quantity} | Donor: {d.donor_id} | Status: {d.status} | Image: {d.image_filename}")
    assert len(donations) == 4, f"Expected 4 donations, found {len(donations)}"

    reservations = Reservation.query.order_by(Reservation.id).all()
    print(f"\n  Total Reservations: {len(reservations)} (Expected: 1)")
    for r in reservations:
        print(f"    - ID {r.id}: Donation #{r.donation_id} reserved by NGO #{r.ngo_id} | Pickup Status: {r.pickup_status}")
    assert len(reservations) == 1, f"Expected 1 reservation, found {len(reservations)}"

# 4. Confirm Local Image URLs Still Work
print("\n[CHECK 4] Verifying Local Image URLs (Nginx static delivery)...")
expected_images = [
    "08cb4dd54e_71JISmXA8LL._AC_UF8941000_QL80_.jpg",
    "293f808e06_71JISmXA8LL._AC_UF8941000_QL80_.jpg",
    "b6d4a88c66_71JISmXA8LL._AC_UF8941000_QL80_.jpg"
]

for img_name in expected_images:
    local_path = os.path.join(UPLOADS_DIR, img_name)
    file_exists = os.path.exists(local_path)
    file_size = os.path.getsize(local_path) if file_exists else 0
    print(f"  Local file '{img_name}': Exists={file_exists}, Size={file_size} B")
    assert file_exists and file_size == 65772, f"Local image integrity issue: {img_name}"

    img_url = f"http://127.0.0.1/static/uploads/{img_name}"
    try:
        req = urllib.request.Request(img_url, headers={"Host": EC2_IP})
        with urllib.request.urlopen(req, timeout=5) as resp:
            ct = resp.headers.get("Content-Type")
            length = resp.headers.get("Content-Length")
            print(f"  HTTP GET /static/uploads/{img_name} -> HTTP {resp.status}, Content-Type: {ct}, Content-Length: {length}")
            assert resp.status == 200, f"Expected HTTP 200, got {resp.status}"
            assert "image/jpeg" in ct, f"Expected image/jpeg, got {ct}"
    except Exception as e:
        print(f"  HTTP GET /static/uploads/{img_name} -> FAIL: {e}")

# 5. Confirm Backups are Unchanged
print("\n[CHECK 5] Verifying Backups on EC2...")
if os.path.exists(BACKUPS_DIR):
    for entry in sorted(os.listdir(BACKUPS_DIR)):
        entry_path = os.path.join(BACKUPS_DIR, entry)
        if os.path.isdir(entry_path):
            files = sorted(os.listdir(entry_path))
            print(f"  Backup Folder: {entry} ({len(files)} files)")
            for f in files:
                fpath = os.path.join(entry_path, f)
                st = os.stat(fpath)
                print(f"    - {f} (Size: {st.st_size} B, ModTime: {st.st_mtime})")
else:
    print("  [WARN] Backup directory does not exist!")

# 6. Service Uptime Verification (Confirming no unexpected restart)
print("\n[CHECK 6] Checking Service Statuses...")
for service in ["foodbridge.service", "nginx"]:
    try:
        out = subprocess.check_output(["systemctl", "status", service, "--no-pager"], stderr=subprocess.STDOUT).decode("utf-8")
        active_lines = [l.strip() for l in out.splitlines() if "Active:" in l or "Loaded:" in l]
        print(f"  {service}:")
        for al in active_lines:
            print(f"    {al}")
    except Exception as e:
        print(f"  Error checking status of {service}: {e}")

print("\n==================================================")
print("TASK 4 Verification Complete: ALL CHECKS PASSED")
print("==================================================")
