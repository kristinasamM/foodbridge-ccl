#!/bin/bash
set -ex

# Log all output to /var/log/user-data.log for debugging
exec > >(tee -a /var/log/user-data.log) 2>&1

echo "=========================================================="
echo "Starting FoodBridge Automated EC2 Deployment Setup"
echo "Date: $(date -u)"
echo "Target AWS Account: 879385476807"
echo "=========================================================="

# 1. Update system packages
export DEBIAN_FRONTEND=noninteractive
apt-get update -y
apt-get upgrade -y -o Dpkg::Options::="--force-confdef" -o Dpkg::Options::="--force-confold"
apt-get install -y python3-pip python3-venv python3-dev nginx git curl openssl

# 2. Setup Application Directories
APP_DIR="/var/www/foodbridge"
LOG_DIR="/var/log/foodbridge"

mkdir -p "$APP_DIR"
mkdir -p "$APP_DIR/instance"
mkdir -p "$APP_DIR/static/uploads"
mkdir -p "$APP_DIR/templates"
mkdir -p "$APP_DIR/static/css"
mkdir -p "$LOG_DIR"

# Ensure ubuntu user and www-data have proper ownership and group permissions
chown -R ubuntu:www-data "$APP_DIR" "$LOG_DIR"
chmod -R 775 "$APP_DIR" "$LOG_DIR"

# Ensure persistent directories retain secure group-write permissions
chmod 775 "$APP_DIR/instance"
chmod 775 "$APP_DIR/static/uploads"

# 3. Generate Cryptographically Secure Environment File (.env)
SECRET_KEY=$(openssl rand -hex 32)
cat <<EOF > "$APP_DIR/.env"
FLASK_ENV=production
FLASK_DEBUG=0
SECRET_KEY=${SECRET_KEY}
EOF

chmod 600 "$APP_DIR/.env"
chown ubuntu:ubuntu "$APP_DIR/.env"

# 4. Setup Python Virtual Environment and Install Dependencies
su - ubuntu -c "python3 -m venv $APP_DIR/venv"
su - ubuntu -c "$APP_DIR/venv/bin/pip install --upgrade pip"
su - ubuntu -c "$APP_DIR/venv/bin/pip install gunicorn==22.0.0 Flask>=3.0.0 Flask-SQLAlchemy>=3.1.1 Werkzeug>=3.0.0"

# 5. Create Production WSGI Entrypoint
cat <<'EOF' > "$APP_DIR/wsgi.py"
import os
from app import app

# Inject production SECRET_KEY from environment if available
if os.environ.get("SECRET_KEY"):
    app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY")

# Ensure debug mode is strictly disabled in production
app.config["DEBUG"] = False

if __name__ == "__main__":
    app.run()
EOF
chown ubuntu:ubuntu "$APP_DIR/wsgi.py"
chmod 644 "$APP_DIR/wsgi.py"

# 6. Configure systemd Service for FoodBridge Gunicorn
cat <<EOF > /etc/systemd/system/foodbridge.service
[Unit]
Description=FoodBridge Gunicorn Application Server
After=network.target

[Service]
User=ubuntu
Group=www-data
WorkingDirectory=$APP_DIR
Environment="PATH=$APP_DIR/venv/bin"
EnvironmentFile=$APP_DIR/.env
ExecStart=$APP_DIR/venv/bin/gunicorn \\
    --workers 2 \\
    --bind 127.0.0.1:5000 \\
    --access-logfile $LOG_DIR/access.log \\
    --error-logfile $LOG_DIR/error.log \\
    --timeout 60 \\
    wsgi:app
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload

# 7. Configure Nginx Reverse Proxy
cat <<'EOF' > /etc/nginx/sites-available/foodbridge
server {
    listen 80 default_server;
    listen [::]:80 default_server;
    server_name _;

    client_max_body_size 16M;

    # Serve static assets directly through Nginx
    location /static/ {
        alias /var/www/foodbridge/static/;
        expires 30d;
        add_header Cache-Control "public, no-transform";
    }

    # Proxy dynamic requests to Gunicorn WSGI server
    location / {
        proxy_pass http://127.0.0.1:5000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_redirect off;
        proxy_read_timeout 60s;
        proxy_connect_timeout 60s;
    }
}
EOF

# Enable Nginx configuration
rm -f /etc/nginx/sites-enabled/default
ln -sf /etc/nginx/sites-available/foodbridge /etc/nginx/sites-enabled/foodbridge

nginx -t
systemctl restart nginx
systemctl enable nginx

echo "=========================================================="
echo "FoodBridge EC2 Base Environment Initialized Successfully"
echo "Date: $(date -u)"
echo "=========================================================="
