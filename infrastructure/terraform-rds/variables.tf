# ==============================================================================
# FoodBridge RDS Infrastructure - Variable Declarations
# Configured for AWS Account: 879385476807 (ap-south-1)
# ==============================================================================

variable "aws_region" {
  description = "Target AWS Region"
  type        = string
  default     = "ap-south-1"
}

variable "aws_profile" {
  description = "Named AWS CLI Profile for local authentication"
  type        = string
  default     = "foodbridge-personal"
}

variable "aws_account_id" {
  description = "Strictly enforced AWS Account ID for Kristina"
  type        = string
  default     = "879385476807"
}

variable "project_name" {
  description = "Project name prefix used for resource naming and tagging"
  type        = string
  default     = "FoodBridge"
}

variable "environment" {
  description = "Deployment environment identifier"
  type        = string
  default     = "dev"
}

# ------------------------------------------------------------------------------
# Existing Networking Resource Identifiers (Read-Only References)
# ------------------------------------------------------------------------------

variable "vpc_id" {
  description = "ID of the existing FoodBridge VPC"
  type        = string
  default     = "vpc-03b6350686167f340"
}

variable "private_subnet_a_id" {
  description = "ID of existing Private Subnet A in ap-south-1a"
  type        = string
  default     = "subnet-0f2d17b8fc243fea5"
}

variable "private_subnet_b_id" {
  description = "ID of existing Private Subnet B in ap-south-1b"
  type        = string
  default     = "subnet-09d92be45585ace17"
}

variable "rds_security_group_id" {
  description = "ID of existing FoodBridge RDS Security Group"
  type        = string
  default     = "sg-0afb47d635abdda5b"
}

# ------------------------------------------------------------------------------
# RDS MySQL Configuration Variables
# ------------------------------------------------------------------------------

variable "db_identifier" {
  description = "Database instance identifier"
  type        = string
  default     = "foodbridge-mysql-db"
}

variable "db_name" {
  description = "Initial schema/database name to create in MySQL"
  type        = string
  default     = "foodbridge"
}

variable "db_username" {
  description = "Master administrative username for the RDS database"
  type        = string
  default     = "foodbridge_admin"
}

variable "engine_version" {
  description = "MySQL engine version (supported LTS version in ap-south-1)"
  type        = string
  default     = "8.0.46"
}

variable "instance_class" {
  description = "RDS compute instance class (low-cost Graviton2 recommended)"
  type        = string
  default     = "db.t4g.micro"
}

variable "allocated_storage" {
  description = "Allocated storage size in gigabytes (minimum 20 GB for gp3)"
  type        = number
  default     = 20
}

variable "storage_type" {
  description = "EBS storage type for RDS"
  type        = string
  default     = "gp3"
}

variable "backup_retention_period" {
  description = "Automated backup retention window in days (1 day standard for dev)"
  type        = number
  default     = 1
}

variable "default_tags" {
  description = "Standard resource tags applied to all managed resources"
  type        = map(string)
  default = {
    Project     = "FoodBridge"
    ManagedBy   = "Terraform"
    Environment = "dev"
    Owner       = "Kristina"
  }
}
