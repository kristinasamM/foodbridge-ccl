#!/usr/bin/env python3
"""
Step 18B Controlled Deployment Script
Safely deploys app.py and updates .env on EC2.
"""
import os
import shutil
import subprocess
import sys

def main():
    app_staging = "/home/ubuntu/step18b_staging/app.py"
    app_prod = "/var/www/foodbridge/app.py"
    env_prod = "/var/www/foodbridge/.env"
    
    print("[1/5] Checking staging app.py exists...")
    if not os.path.exists(app_staging):
        print(f"ERROR: {app_staging} does not exist!")
        sys.exit(1)
        
    print("[2/5] Updating /var/www/foodbridge/.env...")
    with open(env_prod, "r") as f:
        env_lines = f.readlines()
        
    env_dict = {}
    for line in env_lines:
        line_s = line.strip()
        if line_s and not line_s.startswith("#") and "=" in line_s:
            k, v = line_s.split("=", 1)
            env_dict[k.strip()] = v.strip()
            
    # Verify existing critical settings
    if env_dict.get("USE_SECRETS_MANAGER") != "true":
        print("ERROR: USE_SECRETS_MANAGER is not true in current .env!")
        sys.exit(1)
    if env_dict.get("USE_S3") != "true":
        print("ERROR: USE_S3 is not true in current .env!")
        sys.exit(1)
        
    # Set SNS configurations
    env_dict["USE_SNS"] = "true"
    env_dict["SNS_TOPIC_ARN"] = "arn:aws:sns:ap-south-1:879385476807:foodbridge-notifications"
    
    # Write updated .env
    temp_env = "/tmp/foodbridge_updated.env"
    with open(temp_env, "w") as f:
        for k, v in env_dict.items():
            f.write(f"{k}={v}\n")
            
    # Copy with correct permissions (0600, ubuntu:www-data)
    shutil.copy(temp_env, env_prod)
    os.remove(temp_env)
    os.chmod(env_prod, 0o600)
    shutil.chown(env_prod, user="ubuntu", group="www-data")
    print("      .env updated with USE_SNS=true and permissions 0600 preserved.")
    
    print("[3/5] Deploying app.py to production...")
    shutil.copy(app_staging, app_prod)
    os.chmod(app_prod, 0o664)
    shutil.chown(app_prod, user="ubuntu", group="www-data")
    print("      app.py copied with permissions 0664 (ubuntu:www-data).")
    
    print("[4/5] Restarting foodbridge.service...")
    res = subprocess.run(["sudo", "systemctl", "restart", "foodbridge.service"], capture_output=True, text=True)
    if res.returncode != 0:
        print(f"ERROR restarting service: {res.stderr}")
        sys.exit(1)
        
    print("[5/5] Checking service status...")
    status_res = subprocess.run(["systemctl", "is-active", "foodbridge.service"], capture_output=True, text=True)
    status = status_res.stdout.strip()
    print(f"      foodbridge.service status: {status}")
    if status != "active":
        print("ERROR: Service is not active!")
        sys.exit(1)
        
    print("\nSUCCESS: Deployment complete.")

if __name__ == "__main__":
    main()
