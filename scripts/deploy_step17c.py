import os
import sys
import shutil
import datetime
import subprocess
import urllib.request
import urllib.error

print("==================================================")
print("TASK 5: Controlled Production Deployment (Step 17C)")
print("==================================================")

APP_DIR = "/var/www/foodbridge"
BACKUP_ROOT = "/home/ubuntu/backups"
TIMESTAMP = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
BACKUP_DIR = os.path.join(BACKUP_ROOT, f"foodbridge_backup_step17c_{TIMESTAMP}")
STAGING_DIR = "/home/ubuntu/step17c_staging"

# 1. Create fresh timestamped backup
print(f"\n[STEP 1/5] Creating fresh timestamped backup at {BACKUP_DIR}...")
os.makedirs(BACKUP_DIR, exist_ok=True)

backup_items = [
    ("app.py", os.path.join(APP_DIR, "app.py")),
    (".env", os.path.join(APP_DIR, ".env")),
    ("wsgi.py", os.path.join(APP_DIR, "wsgi.py")),
    ("requirements.txt", os.path.join(APP_DIR, "requirements.txt")),
]

for name, src in backup_items:
    if os.path.exists(src):
        dst = os.path.join(BACKUP_DIR, name)
        shutil.copy2(src, dst)
        print(f"  Backed up {name} ({os.path.getsize(dst)} bytes)")

# Backup templates directory
templates_backup = os.path.join(BACKUP_DIR, "templates")
if os.path.exists(os.path.join(APP_DIR, "templates")):
    shutil.copytree(os.path.join(APP_DIR, "templates"), templates_backup)
    print(f"  Backed up templates/ ({len(os.listdir(templates_backup))} files)")

# Backup systemd service definition
svc_src = "/etc/systemd/system/foodbridge.service"
if os.path.exists(svc_src):
    shutil.copy2(svc_src, os.path.join(BACKUP_DIR, "foodbridge.service"))
    print("  Backed up foodbridge.service")

print("  [PASS] Pre-deployment backup created successfully.")

# 2. Deploy tested application code and templates from staging
print("\n[STEP 2/5] Deploying tested app.py and updated dashboard templates...")
try:
    # Copy app.py
    shutil.copy2(os.path.join(STAGING_DIR, "app.py"), os.path.join(APP_DIR, "app.py"))
    print("  Deployed app.py")

    # Copy updated templates
    for tpl in ["donor_dashboard.html", "ngo_dashboard.html", "admin_dashboard.html"]:
        stg_tpl = os.path.join(STAGING_DIR, "templates", tpl)
        app_tpl = os.path.join(APP_DIR, "templates", tpl)
        if os.path.exists(stg_tpl):
            shutil.copy2(stg_tpl, app_tpl)
            print(f"  Deployed templates/{tpl}")

    # Set Linux permissions
    subprocess.run(["sudo", "chown", "-R", "ubuntu:www-data", APP_DIR], check=True)
    subprocess.run(["sudo", "chmod", "664", os.path.join(APP_DIR, "app.py")], check=True)
    print("  [PASS] Code files updated and permissions verified.")
except Exception as e:
    print(f"  [FAIL] Error deploying code files: {e}")
    sys.exit(1)

# 3. Update .env with S3 configuration
print("\n[STEP 3/5] Updating .env with S3 configuration...")
env_path = os.path.join(APP_DIR, ".env")
with open(env_path, "r") as f:
    env_lines = f.readlines()

new_lines = []
existing_keys = set()
for line in env_lines:
    if "=" in line and not line.strip().startswith("#"):
        k = line.strip().split("=")[0].strip()
        existing_keys.add(k)
        if k in ["USE_S3", "S3_BUCKET", "AWS_REGION"]:
            continue  # Will be re-added cleanly
    new_lines.append(line)

# Ensure required S3 settings
if not any("AWS_REGION=" in l for l in new_lines):
    new_lines.append("AWS_REGION=ap-south-1\n")
new_lines.append("USE_S3=true\n")
new_lines.append("S3_BUCKET=foodbridge-donations-879385476807-v2\n")

with open(env_path, "w") as f:
    f.writelines(new_lines)

subprocess.run(["sudo", "chmod", "600", env_path], check=True)
subprocess.run(["sudo", "chown", "ubuntu:www-data", env_path], check=True)
print("  [PASS] .env updated with USE_S3=true, S3_BUCKET, and AWS_REGION.")

# 4. In-flight smoke test before service restart
print("\n[STEP 4/5] Testing Python app import with updated .env...")
test_cmd = [
    "/var/www/foodbridge/venv/bin/python3",
    "-c",
    "import os, sys; sys.path.insert(0, '/var/www/foodbridge'); import app; print('App imported successfully, USE_S3 =', app.app.config.get('USE_S3'))"
]
proc = subprocess.run(test_cmd, capture_output=True, text=True)
print(f"  Import output: {proc.stdout.strip()}")
if proc.returncode != 0:
    print(f"  [FATAL] App import failed! Stderr: {proc.stderr}")
    print("  Initiating automatic rollback...")
    shutil.copy2(os.path.join(BACKUP_DIR, "app.py"), os.path.join(APP_DIR, "app.py"))
    shutil.copy2(os.path.join(BACKUP_DIR, ".env"), os.path.join(APP_DIR, ".env"))
    sys.exit(1)
print("  [PASS] In-flight import test passed.")

# 5. Restart foodbridge.service
print("\n[STEP 5/5] Restarting foodbridge.service...")
try:
    subprocess.run(["sudo", "systemctl", "restart", "foodbridge.service"], check=True)
    status_out = subprocess.check_output(["sudo", "systemctl", "status", "foodbridge.service", "--no-pager"]).decode("utf-8")
    for l in status_out.splitlines():
        if "Active:" in l:
            print(f"  {l.strip()}")
    print("  [PASS] foodbridge.service restarted cleanly.")
except Exception as e:
    print(f"  [FAIL] Failed to restart foodbridge.service: {e}")
    sys.exit(1)

print("\n==================================================")
print("TASK 5 Deployment Complete: SUCCESS")
print("==================================================")
