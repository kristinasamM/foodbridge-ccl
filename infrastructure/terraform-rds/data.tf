# ==============================================================================
# FoodBridge RDS Infrastructure - Data Sources
# Safely references existing networking and security groups without modifying them
# ==============================================================================

# 1. Reference the existing FoodBridge VPC
data "aws_vpc" "existing_vpc" {
  id = var.vpc_id
}

# 2. Reference existing Private Subnet A (ap-south-1a)
data "aws_subnet" "private_subnet_a" {
  id = var.private_subnet_a_id
}

# 3. Reference existing Private Subnet B (ap-south-1b)
data "aws_subnet" "private_subnet_b" {
  id = var.private_subnet_b_id
}

# 4. Reference existing FoodBridge RDS Security Group
data "aws_security_group" "existing_rds_sg" {
  id = var.rds_security_group_id
}

# Resolved local identifiers
locals {
  target_vpc_id = data.aws_vpc.existing_vpc.id
  target_subnet_ids = [
    data.aws_subnet.private_subnet_a.id,
    data.aws_subnet.private_subnet_b.id
  ]
  target_rds_sg_id = data.aws_security_group.existing_rds_sg.id
}
