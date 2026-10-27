# FoodBridge Infrastructure as Code (Terraform)

This directory contains the Terraform configuration for provisioning the cloud infrastructure for the **FoodBridge** application on Amazon Web Services (AWS).

---

## Step 6 Architecture: Custom VPC & Networking

This step sets up a secure, multi-tier network topology following AWS Well-Architected best practices, without incurring unnecessary costs.

### Network Components

| Resource | Identifier / Name | CIDR / Port | Placement / Purpose |
| :--- | :--- | :--- | :--- |
| **VPC** | `FoodBridge-VPC` | `10.0.0.0/16` | Main VPC with DNS hostnames and resolution enabled |
| **Public Subnet** | `FoodBridge-Public-Subnet-1` | `10.0.1.0/24` | `ap-south-1a`, auto-assign public IP enabled (for EC2 Web App) |
| **Private Subnet A** | `FoodBridge-Private-Subnet-A` | `10.0.2.0/24` | `ap-south-1a`, no public IPs (for RDS MySQL primary) |
| **Private Subnet B** | `FoodBridge-Private-Subnet-B` | `10.0.3.0/24` | `ap-south-1b`, no public IPs (for RDS DB Subnet Group multi-AZ) |
| **Internet Gateway** | `FoodBridge-IGW` | — | Attached to `FoodBridge-VPC` for inbound/outbound internet |
| **Public Route Table** | `FoodBridge-Public-RT` | `0.0.0.0/0 -> IGW` | Associated with `FoodBridge-Public-Subnet-1` |
| **Private Route Table**| `FoodBridge-Private-RT` | Internal only | Associated with Private Subnet A & B; **no internet route** |
| **EC2 Security Group** | `FoodBridge-EC2-SG` | In: 80 (HTTP 0.0.0.0/0), 22 (SSH Trusted IP)<br>Out: All traffic | Firewall for the Flask EC2 instance |
| **RDS Security Group** | `FoodBridge-RDS-SG` | In: 3306 (MySQL from `FoodBridge-EC2-SG` only)<br>Out: All traffic | Firewall strictly isolating database tier |

> [!NOTE]
> **Zero Hourly Cost Architecture:**  
> This step does **not** create any NAT Gateways, Elastic IPs, EC2 instances, RDS instances, Application Load Balancers, or paid VPC Endpoints. VPCs, subnets, route tables, internet gateways, and security groups in AWS carry **no hourly charge**.

---

## File Structure

```text
infrastructure/terraform/
├── .gitignore               # Ignores Terraform state files and credentials
├── README.md                # Deployment and verification documentation
├── network.tf               # VPC, subnets, IGW, route tables, associations
├── outputs.tf               # Exposed IDs and attributes
├── providers.tf             # AWS provider configuration
├── security.tf              # EC2 and RDS security groups
├── terraform.tfvars.example # Example variable values
├── variables.tf             # Variable declarations with types and defaults
└── versions.tf              # Required Terraform and provider versions
```

---

## Prerequisites

1. **AWS CLI v2** (Installed on this system: `aws-cli/2.36.14`).
2. **Terraform CLI** (`>= 1.5.0`):
   - Install via Windows Package Manager:
     ```powershell
     winget install HashiCorp.Terraform
     ```
   - Or download directly from [Terraform Releases](https://releases.hashicorp.com/terraform/) and add the directory containing `terraform.exe` to your `PATH`.
3. **Active AWS Credentials**:
   - Verify identity using:
     ```powershell
     aws sts get-caller-identity
     ```
   - If expired or unconfigured, authenticate with:
     ```powershell
     aws configure
     ```
     or if using AWS IAM Identity Center:
     ```powershell
     aws sso login
     ```

---

## Deployment Workflow

### 1. Configure Variables

Create your local variable file (ignored by Git):

```powershell
Copy-Item terraform.tfvars.example terraform.tfvars
```

Edit `terraform.tfvars` to set `trusted_ssh_cidr` to your specific public IP (e.g., `203.0.113.25/32`) rather than `0.0.0.0/0` for production security.

### 2. Initialize Working Directory

Download the AWS provider plugin:

```powershell
terraform init
```

### 3. Format and Validate

Check syntax and configuration validity:

```powershell
terraform fmt
terraform validate
```

### 4. Review Execution Plan

Preview the exact 11 resources that Terraform will manage:

```powershell
terraform plan
```

### 5. Apply (Deploy to AWS)

*Run this only when you are ready to provision the VPC and security groups:*

```powershell
terraform apply
```

Review the printed execution plan and type `yes` to confirm.

---

## Verification Instructions

After running `terraform apply`, verify the provisioned resources either in the AWS Console or using the AWS CLI:

### 1. Verify VPC
```powershell
aws ec2 describe-vpcs --filters "Name=tag:Name,Values=FoodBridge-VPC" --region ap-south-1 --query "Vpcs[*].[VpcId,CidrBlock,State]" --output table
```

### 2. Verify Subnets
```powershell
aws ec2 describe-subnets --filters "Name=tag:Project,Values=FoodBridge" --region ap-south-1 --query "Subnets[*].[SubnetId,CidrBlock,AvailabilityZone,MapPublicIpOnLaunch,Tags[?Key=='Name'].Value|[0]]" --output table
```

### 3. Verify Route Tables
```powershell
aws ec2 describe-route-tables --filters "Name=tag:Project,Values=FoodBridge" --region ap-south-1 --query "RouteTables[*].[RouteTableId,Tags[?Key=='Name'].Value|[0],Routes]" --output json
```

### 4. Verify Security Groups
```powershell
aws ec2 describe-security-groups --filters "Name=tag:Project,Values=FoodBridge" --region ap-south-1 --query "SecurityGroups[*].[GroupId,GroupName,Description]" --output table
```

---

## Teardown / Cleanup

If you ever need to destroy all networking resources created by this configuration:

```powershell
terraform destroy
```
