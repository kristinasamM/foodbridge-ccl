# ==============================================================================
# FoodBridge Application Sync & Deployment Script (Windows PowerShell)
# Target AWS Account: 879385476807 (ap-south-1)
# Deploys code to Ubuntu EC2 without overwriting persistent database or uploads
# ==============================================================================

param (
    [string]$KeyPath = "$HOME\.ssh\foodbridge-key.pem",
    [string]$InstanceIp = "",
    [string]$TerraformDir = "infrastructure/terraform-ec2"
)

$ErrorActionPreference = "Stop"

Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host "FoodBridge EC2 Application Deployment (Windows PowerShell)" -ForegroundColor Cyan
Write-Host "==========================================================" -ForegroundColor Cyan

# 1. Auto-fetch public IP from Terraform if not explicitly provided
if (-not $InstanceIp) {
    if (Test-Path $TerraformDir) {
        Write-Host "[1/5] Fetching EC2 Public IP from Terraform ($TerraformDir)..." -ForegroundColor Cyan
        try {
            $InstanceIp = (terraform -chdir="$TerraformDir" output -raw ec2_public_ip 2>$null).Trim()
        } catch {
            $InstanceIp = ""
        }
    }
}

if (-not $InstanceIp) {
    Write-Warning "Could not automatically determine EC2 instance IP from Terraform."
    $InstanceIp = Read-Host "Please enter the public IPv4 address of your EC2 instance"
    if (-not $InstanceIp) {
        Write-Error "No target IP provided. Deployment aborted."
        exit 1
    }
}

Write-Host "Target EC2 Instance IP: $InstanceIp" -ForegroundColor Green

# 2. Verify SSH key file exists
if (-not (Test-Path $KeyPath)) {
    $downloadsKey = Join-Path (Join-Path $HOME "Downloads") "foodbridge-key.pem"
    if (Test-Path $downloadsKey) {
        $KeyPath = $downloadsKey
    } else {
        Write-Warning "SSH Key file '$KeyPath' not found."
        $KeyPath = Read-Host "Please enter the full path to your private key (.pem) file"
        if (-not (Test-Path $KeyPath)) {
            Write-Error "Invalid key file path. Deployment aborted."
            exit 1
        }
    }
}

Write-Host "Using Private Key: $KeyPath" -ForegroundColor Green

# 3. Create temporary staging directory for clean code transfer
Write-Host "[2/5] Creating temporary staging directory..." -ForegroundColor Cyan
$StagingDir = Join-Path $env:TEMP ("foodbridge_deploy_" + [guid]::NewGuid().ToString("N"))
New-Item -ItemType Directory -Path $StagingDir -Force | Out-Null

try {
    # Copy essential application code
    Copy-Item "app.py" -Destination $StagingDir
    Copy-Item "requirements.txt" -Destination $StagingDir
    Copy-Item -Recurse "templates" -Destination $StagingDir
    
    # Copy static/css only (never copy static/uploads to protect user uploaded images!)
    New-Item -ItemType Directory -Path (Join-Path $StagingDir "static") -Force | Out-Null
    Copy-Item -Recurse "static\css" -Destination (Join-Path $StagingDir "static")

    # 4. Transfer files via SCP
    Write-Host "[3/5] Transferring application files to EC2 via SCP..." -ForegroundColor Cyan
    scp -i $KeyPath -o StrictHostKeyChecking=no -r "$StagingDir/*" "ubuntu@${InstanceIp}:/var/www/foodbridge/"

    # 5. Set Linux permissions and restart systemd service
    Write-Host "[4/5] Setting file ownership and restarting services..." -ForegroundColor Cyan
    ssh -i $KeyPath -o StrictHostKeyChecking=no "ubuntu@${InstanceIp}" @"
        sudo chown -R ubuntu:www-data /var/www/foodbridge
        sudo chmod -R 775 /var/www/foodbridge
        sudo chmod 775 /var/www/foodbridge/instance
        sudo chmod 775 /var/www/foodbridge/static/uploads
        sudo systemctl daemon-reload
        sudo systemctl enable foodbridge.service
        sudo systemctl restart foodbridge.service
        sudo systemctl restart nginx
        sudo systemctl status foodbridge.service --no-pager
"@

    # 6. Verify web application health
    Write-Host "[5/5] Verifying web application health..." -ForegroundColor Cyan
    Start-Sleep -Seconds 3
    try {
        $response = Invoke-WebRequest -Uri "http://$InstanceIp" -UseBasicParsing -TimeoutSec 10
        Write-Host "==========================================================" -ForegroundColor Green
        Write-Host "SUCCESS! FoodBridge is live at: http://$InstanceIp" -ForegroundColor Green
        Write-Host "HTTP Status: $($response.StatusCode)" -ForegroundColor Green
        Write-Host "==========================================================" -ForegroundColor Green
    } catch {
        Write-Warning "Health check returned an error or timed out: $_"
        Write-Host "You can inspect server logs via:"
        Write-Host "ssh -i '$KeyPath' ubuntu@$InstanceIp 'sudo journalctl -u foodbridge.service -n 50 --no-pager'"
    }
}
finally {
    if (Test-Path $StagingDir) {
        Remove-Item -Recurse -Force $StagingDir -ErrorAction SilentlyContinue
    }
}
