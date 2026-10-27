#!/usr/bin/env bash
# ==============================================================================
# FoodBridge Application Sync & Deployment Script (Bash)
# Deploys code to Ubuntu EC2 without overwriting persistent database or uploads
# ==============================================================================

set -euo pipefail

KEY_PATH="${1:-$HOME/.ssh/redminekeypair.pem}"
INSTANCE_IP="${2:-}"

if [[ -z "$INSTANCE_IP" ]]; then
    echo "[1/4] Fetching EC2 Public IP from Terraform output..."
    INSTANCE_IP=$(terraform -chdir="infrastructure/terraform" output -raw ec2_public_ip 2>/dev/null || true)
fi

if [[ -z "$INSTANCE_IP" ]]; then
    echo "ERROR: Could not retrieve EC2 IP. Ensure Terraform has provisioned the instance or provide IP as argument."
    exit 1
fi

echo "Target EC2 Instance: $INSTANCE_IP"

# 2. Transfer application code (preserving SQLite instance/ and static/uploads/)
echo "[2/4] Syncing application code via rsync/scp..."
rsync -avz -e "ssh -i $KEY_PATH -o StrictHostKeyChecking=no" \
    --exclude="instance/" \
    --exclude="static/uploads/" \
    --exclude="venv/" \
    --exclude="__pycache__/" \
    --exclude=".git/" \
    ./ "ubuntu@${INSTANCE_IP}:/var/www/foodbridge/"

# 3. Restart services
echo "[3/4] Updating file ownership and restarting services..."
ssh -i "$KEY_PATH" -o StrictHostKeyChecking=no "ubuntu@${INSTANCE_IP}" "
    sudo chown -R ubuntu:www-data /var/www/foodbridge
    sudo chmod -R 775 /var/www/foodbridge
    sudo systemctl restart foodbridge.service
    sudo systemctl restart nginx
    sudo systemctl status foodbridge.service --no-pager
"

# 4. Verify HTTP Response
echo "[4/4] Verifying HTTP response..."
curl -Is "http://${INSTANCE_IP}" | head -n 5
echo "SUCCESS: FoodBridge is available at http://${INSTANCE_IP}"
