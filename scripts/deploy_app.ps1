# ==============================================================================
# FoodBridge Application Sync & Deployment Script (Windows PowerShell)
# Deploys code to Ubuntu EC2 without overwriting persistent database or uploads
# ==============================================================================

param (
    [string]$KeyPath = "$HOME\.ssh\redminekeypair.pem",
    [string]$InstanceIp = ""
)

$ErrorActionPreference = "Stop"

# Auto-fetch public IP from Terraform if not provided
if (-not $InstanceIp) {
    Write-Host "[1/5] Fetching EC2 Public IP from Terraform output..." -ForegroundColor Cyan
    $InstanceIp = (terraform -chdir="infrastructure/terraform" output -raw ec2_public_ip).Trim()
}

if (-not $InstanceIp) {
    Write-Error "Could not determine EC2 instance IP. Please ensure Terraform has deployed the instance or pass -InstanceIp."
    exit 1
}

Write-Host "Target EC2 Instance IP: $InstanceIp" -ForegroundColor Green

# Verify SSH key file exists
if (-not (Test-Path $KeyPath)) {
    Write-Warning "SSH Key file '$KeyPath' not found."
    $KeyPath = Read-Host "Please enter the full path to your private key (.pem) file"
    if (-not (Test-Path $KeyPath)) {
        Write-Error "Invalid key path. Aborting."
        exit 1
    }
}

Write-Host "[2/5] Creating temporary staging directory for deployment..." -ForegroundColor Cyan
$StagingDir = Join-Path $env:TEMP ("foodbridge_deploy_" + [guid]::NewGuid().ToString("N"))
New-Item -ItemType Directory -Path $StagingDir -Force | Out-Null

try {
    # Copy code files (explicitly excluding SQLite database and user uploads!)
    Copy-Item "app.py" -Destination $StagingDir
    Copy-Item "requirements.txt" -Destination $StagingDir
    Copy-Item -Recurse "templates" -Destination $StagingDir
    
    # Copy static/css only (never copy static/uploads to protect user files!)
    New-Item -ItemType Directory -Path (Join-Path $StagingDir "static") -Force | Out-Null
    Copy-Item -Recurse "static\css" -Destination (Join-Path $StagingDir "static")

    Write-Host "[3/5] Transferring application files to EC2 via SCP..." -ForegroundColor Cyan
    scp -i $KeyPath -o StrictHostKeyChecking=no -r "$StagingDir/*" "ubuntu@${InstanceIp}:/var/www/foodbridge/"

    Write-Host "[4/5] Setting permissions and restarting FoodBridge systemd service..." -ForegroundColor Cyan
    ssh -i $KeyPath -o StrictHostKeyChecking=no "ubuntu@${InstanceIp}" @"
        sudo chown -R ubuntu:www-data /var/www/foodbridge
        sudo chmod -R 775 /var/www/foodbridge
        sudo chmod 775 /var/www/foodbridge/instance
        sudo chmod 775 /var/www/foodbridge/static/uploads
        sudo systemctl restart foodbridge.service
        sudo systemctl restart nginx
        sudo systemctl status foodbridge.service --no-pager
"@

    Write-Host "[5/5] Verifying web application health..." -ForegroundColor Cyan
    Start-Sleep -Seconds 3
    try {
        $response = Invoke-WebRequest -Uri "http://$InstanceIp" -UseBasicParsing -TimeoutSec 10
        Write-Host "SUCCESS! FoodBridge is live at: http://$InstanceIp (Status: $($response.StatusCode))" -ForegroundColor Green
    } catch {
        Write-Warning "Health check returned an error or timed out: $_"
        Write-Host "Check logs via: ssh -i $KeyPath ubuntu@$InstanceIp 'sudo journalctl -u foodbridge.service -n 50'"
    }
}
finally {
    if (Test-Path $StagingDir) {
        Remove-Item -Recurse -Force $StagingDir -ErrorAction SilentlyContinue
    }
}
