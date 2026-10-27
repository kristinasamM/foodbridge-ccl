# ==============================================================================
# FoodBridge EC2 Infrastructure - Data Sources
# Discovers existing manually created networking resources without recreating them
# ==============================================================================

# 1. Reference the user's existing manually created VPC (vpc-03b6350686167f340)
data "aws_vpc" "existing_vpc" {
  id = var.vpc_id
}

# 2. Discover the existing Public Subnet (10.0.1.0/24) if explicit ID is not provided
data "aws_subnet" "discovered_public" {
  count = var.public_subnet_id == "" ? 1 : 0

  vpc_id     = data.aws_vpc.existing_vpc.id
  cidr_block = var.public_subnet_cidr
}

# 3. Discover the existing EC2 Security Group by VPC ID & Name if explicit ID is not provided
data "aws_security_group" "discovered_ec2_sg" {
  count = var.ec2_security_group_id == "" ? 1 : 0

  vpc_id = data.aws_vpc.existing_vpc.id
  name   = var.ec2_security_group_name
}

# 4. Discover the official Canonical Ubuntu 24.04 LTS (Noble Numbat) AMI in ap-south-1
data "aws_ami" "ubuntu_noble" {
  most_recent = true
  owners      = ["099720109477"] # Canonical

  filter {
    name   = "name"
    values = ["ubuntu/images/hvm-ssd-gp3/ubuntu-noble-24.04-amd64-server-*"]
  }

  filter {
    name   = "virtualization-type"
    values = ["hvm"]
  }
}

# Resolved local identifiers
locals {
  target_subnet_id = var.public_subnet_id != "" ? var.public_subnet_id : data.aws_subnet.discovered_public[0].id
  target_sg_id     = var.ec2_security_group_id != "" ? var.ec2_security_group_id : data.aws_security_group.discovered_ec2_sg[0].id
  target_ami_id    = var.ec2_ami_id != "" ? var.ec2_ami_id : data.aws_ami.ubuntu_noble.id
}
