variable "aws_region" {
  type        = string
  description = "Target AWS region for deploying resources"
  default     = "ap-south-1"
}

variable "aws_profile" {
  type        = string
  description = "AWS CLI named profile to use for authentication"
  default     = "foodbridge-personal"
}

variable "project_name" {
  type        = string
  description = "Name of the project used for naming and resource tagging"
  default     = "FoodBridge"
}

variable "environment" {
  type        = string
  description = "Deployment environment (e.g., dev, staging, prod)"
  default     = "dev"
}

variable "vpc_cidr" {
  type        = string
  description = "CIDR block for the custom VPC"
  default     = "10.0.0.0/16"
}

variable "public_subnet_cidr" {
  type        = string
  description = "CIDR block for the public subnet"
  default     = "10.0.1.0/24"
}

variable "private_subnet_a_cidr" {
  type        = string
  description = "CIDR block for Private Subnet A"
  default     = "10.0.2.0/24"
}

variable "private_subnet_b_cidr" {
  type        = string
  description = "CIDR block for Private Subnet B"
  default     = "10.0.3.0/24"
}

variable "availability_zones" {
  type        = list(string)
  description = "List of distinct Availability Zones for subnet placement"
  default     = ["ap-south-1a", "ap-south-1b"]

  validation {
    condition     = length(var.availability_zones) >= 2 && var.availability_zones[0] != var.availability_zones[1]
    error_message = "At least two distinct availability zones must be specified."
  }
}

variable "trusted_ssh_cidr" {
  type        = string
  description = "Configurable trusted IPv4 CIDR allowed to connect to SSH (port 22). Must be restricted to your specific IP address (e.g. '203.0.113.25/32') for security."

  validation {
    condition     = var.trusted_ssh_cidr != "0.0.0.0/0"
    error_message = "trusted_ssh_cidr must not be 0.0.0.0/0. Please provide a specific trusted IP/CIDR (e.g., '203.0.113.25/32')."
  }
}

variable "default_tags" {
  type        = map(string)
  description = "Default resource tags applied to all AWS resources"
  default = {
    Project     = "FoodBridge"
    ManagedBy   = "Terraform"
    Environment = "dev"
  }
}

# ==============================================================================
# EC2 Instance Configuration (Step 7)
# ==============================================================================

variable "instance_type" {
  type        = string
  description = "EC2 instance type for FoodBridge web server (t3.micro is Free Tier eligible)"
  default     = "t3.micro"
}

variable "ec2_ami_id" {
  type        = string
  description = "AMI ID for Ubuntu 24.04 LTS (Noble Numbat) in ap-south-1"
  default     = "ami-065d2b03fb493085a"
}

variable "root_volume_size" {
  type        = number
  description = "Size of the encrypted root EBS gp3 volume in GB"
  default     = 20

  validation {
    condition     = var.root_volume_size >= 10 && var.root_volume_size <= 30
    error_message = "Root volume size should be between 10 GB and 30 GB to stay within AWS Free Tier limits."
  }
}

variable "ssh_key_name" {
  type        = string
  description = "Name of existing EC2 Key Pair for SSH access (optional, leave blank if no key pair)"
  default     = "redminekeypair"
}
