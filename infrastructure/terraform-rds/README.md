# FoodBridge RDS Infrastructure (Terraform)

This directory contains the dedicated, isolated Terraform configuration for provisioning the **Amazon RDS MySQL** database for the **FoodBridge** application in Kristina's AWS account.

---

## Architecture Overview

```text
[ Kristina's VPC: FoodBridge-VPC (10.0.0.0/16) ]
  ├── Public Subnet (10.0.1.0/24)
  │     └── EC2 Web Server (FoodBridge-EC2-SG: 80, 22)
  │           │
  │           │ MySQL TCP 3306 (Internal VPC Traffic Only)
  │           ▼
  └── Private Subnets (DB Subnet Group)
        ├── FoodBridge-Private-Subnet-A (10.0.2.0/24 in ap-south-1a)
        └── FoodBridge-Private-Subnet-B (10.0.3.0/24 in ap-south-1b)
              └── RDS MySQL (FoodBridge-RDS-SG: 3306 from EC2-SG)
                    ├── Engine: MySQL 8.0.46
                    ├── Class: db.t4g.micro (Single-AZ)
                    ├── Storage: 20 GB gp3 (Autoscaling Disabled)
                    └── Master Secret: AWS Secrets Manager (Auto-managed)
```

---

## Strict Account Isolation & Security Guardrails

1. **Target Account Lockdown:**  
   `providers.tf` explicitly enforces `allowed_account_ids = ["879385476807"]`. It is technically impossible to apply this configuration to any other AWS account.
2. **Zero Contamination from Parth's Account:**  
   This directory does not read, reference, or import state from `infrastructure/terraform` or account `719572785129`.
3. **No Hardcoded Passwords:**  
   `manage_master_user_password = true` delegates administrative password generation and storage to AWS Secrets Manager. No plaintext passwords exist in `.tf` files, `.tfvars`, or Terraform state.
4. **Network Isolation:**  
   `publicly_accessible = false` ensures the database is placed exclusively in private subnets with no public IPv4 address.
5. **Accidental Deletion Protection:**  
   `deletion_protection = true` and `skip_final_snapshot = false` protect against unintended termination.

---

## Cost Optimization Highlights

- **Instance Class:** `db.t4g.micro` (~$0.0176/hour on AWS Graviton2, lowest cost in `ap-south-1`).
- **Single-AZ:** `multi_az = false` avoids doubling compute and storage costs.
- **Storage Autoscaling Disabled:** `max_allocated_storage = 0` prevents unexpected storage growth billing.
- **Telemetry Limits:** Enhanced Monitoring and Performance Insights are disabled to eliminate auxiliary telemetry charges.
- **Estimated Operating Cost:** ~$0.50/day if running 24/7 (~$0.10 for a 5-hour test session).

---

## File Structure

```text
infrastructure/terraform-rds/
├── .gitignore               # Excludes state files, local overrides, crash logs
├── README.md                # Module architecture and operations guide
├── data.tf                  # Read-only lookups for existing VPC, subnets, SG
├── main.tf                  # DB Subnet Group and RDS MySQL instance
├── outputs.tf               # Connection parameters and Secret ARN
├── providers.tf             # AWS provider with account lock (879385476807)
├── terraform.tfvars         # Pre-configured active variables
├── terraform.tfvars.example # Sanitized template for version control
├── variables.tf             # Typed variable declarations with defaults
└── versions.tf              # Terraform >= 1.5.0 and AWS ~> 5.0 constraints
```
