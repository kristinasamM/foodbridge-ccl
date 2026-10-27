import os
import shutil
import datetime

BACKUP_ROOT = "/home/ubuntu/backups"
TIMESTAMP = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
BACKUP_DIR = os.path.join(BACKUP_ROOT, f"foodbridge_backup_step18b_{TIMESTAMP}")
APP_DIR = "/var/www/foodbridge"

os.makedirs(BACKUP_DIR, exist_ok=True)
print(f"Creating Step 18B Backup at: {BACKUP_DIR}")

# Copy core files
files_to_backup = ["app.py", ".env", "requirements.txt", "wsgi.py"]
for f in files_to_backup:
    src = os.path.join(APP_DIR, f)
    if os.path.exists(src):
        shutil.copy2(src, os.path.join(BACKUP_DIR, f))
        print(f"  Backed up {f} ({os.path.getsize(src)} B)")

# Copy service file
svc_path = "/etc/systemd/system/foodbridge.service"
if os.path.exists(svc_path):
    shutil.copy2(svc_path, os.path.join(BACKUP_DIR, "foodbridge.service"))
    print(f"  Backed up foodbridge.service")

# Copy templates
tpl_dst = os.path.join(BACKUP_DIR, "templates")
tpl_src = os.path.join(APP_DIR, "templates")
if os.path.exists(tpl_src):
    shutil.copytree(tpl_src, tpl_dst)
    print(f"  Backed up templates/ ({len(os.listdir(tpl_dst))} templates)")

print(f"[SUCCESS] Step 18B Backup complete at: {BACKUP_DIR}")
