# ==============================================================================
# FoodBridge EC2 Infrastructure - Variables
# Configured for AWS Account: 879385476807 (ap-south-1)
# ==============================================================================

variable "aws_region" {
  type        = string
  description = "Target AWS region for deploying the EC2 instance"
  default     = "ap-south-1"
}

variable "aws_profile" {
  type        = string
  description = "AWS CLI named profile to use for authentication (leave empty to use default profile / environment variables)"
  default     = ""
}

variable "aws_account_id" {
  type        = string
  description = "Target AWS Account ID to enforce as a strict deployment guard"
  default     = "879385476807"
}

variable "project_name" {
  type        = string
  description = "Name of the project used for naming and resource tagging"
  default     = "FoodBridge"
}

variable "environment" {
  type        = string
  description = "Deployment environment identifier"
  default     = "dev"
}

variable "vpc_id" {
  type        = string
  description = "ID of the existing manually created VPC in your account"
  default     = "vpc-03b6350686167f340"
}

variable "public_subnet_id" {
  type        = string
  description = "ID of the manually created Public Subnet (leave empty to auto-discover using VPC ID and CIDR 10.0.1.0/24)"
  default     = ""
}

variable "public_subnet_cidr" {
  type        = string
  description = "CIDR block of the Public Subnet used for discovery when public_subnet_id is not directly specified"
  default     = "10.0.1.0/24"
}

variable "ec2_security_group_id" {
  type        = string
  description = "ID of the manually created EC2 Security Group (leave empty to auto-discover by VPC ID and name 'FoodBridge-EC2-SG')"
  default     = ""
}

variable "ec2_security_group_name" {
  type        = string
  description = "Name or tag of the manually created EC2 Security Group used for lookup"
  default     = "FoodBridge-EC2-SG"
}

variable "instance_type" {
  type        = string
  description = "EC2 instance type (t3.micro is eligible for AWS Free Tier in eligible accounts)"
  default     = "t3.micro"
}

variable "ec2_ami_id" {
  type        = string
  description = "Explicit AMI ID for Ubuntu 24.04 LTS in ap-south-1 (leave empty to automatically query latest Canonical release)"
  default     = ""
}

variable "root_volume_size" {
  type        = number
  description = "Size of the root EBS block volume in GB (gp3, encrypted). Keep <= 30 GB for Free Tier eligibility."
  default     = 20

  validation {
    condition     = var.root_volume_size >= 10 && var.root_volume_size <= 30
    error_message = "Root volume size should be between 10 GB and 30 GB to respect AWS Free Tier storage guidelines."
  }
}

variable "ssh_key_name" {
  type        = string
  description = "Name of existing EC2 Key Pair in ap-south-1 for SSH/SCP deployment access (leave empty if no key pair)"
  default     = ""
}

variable "default_tags" {
  type        = map(string)
  description = "Default resource tags applied to all managed AWS resources"
  default = {
    Project     = "FoodBridge"
    ManagedBy   = "Terraform"
    Environment = "dev"
    Owner       = "Kristina"
  }
}
