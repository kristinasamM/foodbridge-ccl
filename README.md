# FoodBridge - Cloud Computing Lab (CCL)

FoodBridge is a cloud-native web application designed to eliminate food waste by connecting surplus food donors (restaurants, caterers, individuals) with verified NGOs and shelters in real time.

Built as a comprehensive Cloud Computing project demonstrating modern cloud architecture, automated infrastructure provisioning, and secure cloud services integration.

---

## Architecture Overview

- **Web Application**: Flask (Python 3) MVC application with role-based access control (Donors, NGOs, System Administrators).
- **Relational Database**: AWS RDS MySQL with automated failover and dynamic credential retrieval via **AWS Secrets Manager** (IAM role authentication, no plaintext credentials in code).
- **Object Storage**: AWS S3 bucket for storing food donation photos and static verification assets.
- **Push Notifications**: AWS SNS (Simple Notification Service) for real-time donor/claim alerts and operational audit notifications.
- **Serverless Automation**: AWS Lambda triggered by Amazon EventBridge (Cron) executing scheduled automated audits and expiration transitions.
- **Infrastructure as Code (IaC)**: Modular Terraform configurations (`terraform-ec2` and `terraform-rds`) for automated, reproducible cloud provisioning.
- **Instance Management**: AWS Systems Manager (SSM) for secure, keyless remote execution and deployments.

---

## Repository Structure

```
Foodbridge/
├── app.py                     # Main Flask application with routing & business logic
├── requirements.txt           # Python dependencies
├── static/                    # CSS stylesheets, static assets, and media
│   ├── css/style.css
│   └── uploads/
├── templates/                 # Jinja2 HTML templates
│   ├── index.html             # Landing page
│   ├── login.html             # User login
│   ├── register.html          # User registration (Donor/NGO)
│   ├── donor_dashboard.html   # Donor management interface
│   ├── ngo_dashboard.html     # NGO claim interface
│   ├── admin_dashboard.html   # Administrative monitoring portal
│   └── add_donation.html      # Food donation submission form
├── infrastructure/            # Terraform Infrastructure as Code
│   ├── terraform-ec2/         # EC2, IAM roles, security groups
│   └── terraform-rds/         # RDS MySQL instance, subnets, secrets
└── scripts/                   # Automated deployment & operational utilities
    ├── get_rds_credentials.py # AWS Secrets Manager credential resolver
    ├── expire_donations.py    # Automated donation expiry processor
    ├── deploy_app.ps1         # Windows deployment automation
    ├── deploy_app.sh          # Linux/EC2 deployment automation
    └── test_*_suite.py        # Automated test verification suites
```

---

## Local Development Setup

1. **Clone the repository**:
   ```bash
   git clone https://github.com/kristinasamM/foodbridge-ccl.git
   cd foodbridge-ccl
   ```

2. **Create and activate a virtual environment**:
   ```bash
   python -m venv venv
   # On Windows:
   .\venv\Scripts\activate
   # On Linux/macOS:
   source venv/bin/activate
   ```

3. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

4. **Run the application**:
   ```bash
   # By default, runs in local SQLite development mode
   python app.py
   ```
   Open [http://localhost:5000](http://localhost:5000) in your browser.

---

## Cloud Deployment Configuration

To connect the application to AWS RDS in production:
```bash
export USE_SECRETS_MANAGER=true
export RDS_SECRET_NAME=foodbridge/app-db-credentials
export AWS_REGION=ap-south-1
python app.py
```

---

## Security Practices

- **Zero Hardcoded Secrets**: All database and AWS service credentials are dynamically fetched at runtime from AWS Secrets Manager using IAM machine roles.
- **Sanitized Uploads**: Image uploads are validated, hashed, and isolated.
- **Git Hygiene**: Environment files, private keys, local databases (`.db`), and terraform state (`.tfstate`) are excluded from version control via `.gitignore`.
