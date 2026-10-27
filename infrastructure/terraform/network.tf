# ==============================================================================
# FoodBridge AWS Custom VPC & Networking Configuration
# ==============================================================================

# 1. Custom VPC (FoodBridge-VPC)
resource "aws_vpc" "foodbridge_vpc" {
  cidr_block           = var.vpc_cidr
  enable_dns_support   = true
  enable_dns_hostnames = true

  tags = {
    Name = "${var.project_name}-VPC"
  }
}

# 2. Public Subnet (10.0.1.0/24 in AZ 1)
resource "aws_subnet" "public_subnet" {
  vpc_id                  = aws_vpc.foodbridge_vpc.id
  cidr_block              = var.public_subnet_cidr
  availability_zone       = var.availability_zones[0]
  map_public_ip_on_launch = true

  tags = {
    Name = "${var.project_name}-Public-Subnet-1"
    Type = "Public"
  }
}

# 3. Private Subnet A (10.0.2.0/24 in AZ 1)
resource "aws_subnet" "private_subnet_a" {
  vpc_id                  = aws_vpc.foodbridge_vpc.id
  cidr_block              = var.private_subnet_a_cidr
  availability_zone       = var.availability_zones[0]
  map_public_ip_on_launch = false

  tags = {
    Name = "${var.project_name}-Private-Subnet-A"
    Type = "Private"
  }
}

# 4. Private Subnet B (10.0.3.0/24 in AZ 2 - Multi-AZ compliance for RDS)
resource "aws_subnet" "private_subnet_b" {
  vpc_id                  = aws_vpc.foodbridge_vpc.id
  cidr_block              = var.private_subnet_b_cidr
  availability_zone       = var.availability_zones[1]
  map_public_ip_on_launch = false

  tags = {
    Name = "${var.project_name}-Private-Subnet-B"
    Type = "Private"
  }
}

# 5. Internet Gateway
resource "aws_internet_gateway" "igw" {
  vpc_id = aws_vpc.foodbridge_vpc.id

  tags = {
    Name = "${var.project_name}-IGW"
  }
}

# 6. Public Route Table & Default Route to Internet Gateway
resource "aws_route_table" "public_rt" {
  vpc_id = aws_vpc.foodbridge_vpc.id

  tags = {
    Name = "${var.project_name}-Public-RT"
  }
}

resource "aws_route" "public_internet_access" {
  route_table_id         = aws_route_table.public_rt.id
  destination_cidr_block = "0.0.0.0/0"
  gateway_id             = aws_internet_gateway.igw.id
}

# 7. Public Subnet Route Table Association
resource "aws_route_table_association" "public_assoc" {
  subnet_id      = aws_subnet.public_subnet.id
  route_table_id = aws_route_table.public_rt.id
}

# 8. Private Route Table (isolated, strictly no 0.0.0.0/0 route to internet)
resource "aws_route_table" "private_rt" {
  vpc_id = aws_vpc.foodbridge_vpc.id

  tags = {
    Name = "${var.project_name}-Private-RT"
  }
}

# 9. Private Subnet Route Table Associations
resource "aws_route_table_association" "private_assoc_a" {
  subnet_id      = aws_subnet.private_subnet_a.id
  route_table_id = aws_route_table.private_rt.id
}

resource "aws_route_table_association" "private_assoc_b" {
  subnet_id      = aws_subnet.private_subnet_b.id
  route_table_id = aws_route_table.private_rt.id
}
