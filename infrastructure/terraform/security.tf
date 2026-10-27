# ==============================================================================
# FoodBridge Security Groups Configuration
# ==============================================================================

# 1. EC2 Security Group
# Allows HTTP (port 80) from anywhere and SSH (port 22) restricted to trusted CIDR
resource "aws_security_group" "ec2_sg" {
  name        = "${var.project_name}-EC2-SG"
  description = "Security group for FoodBridge EC2 web application instances"
  vpc_id      = aws_vpc.foodbridge_vpc.id

  ingress {
    description = "Allow inbound HTTP access from anywhere"
    from_port   = 80
    to_port     = 80
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  ingress {
    description = "Allow inbound SSH access from trusted CIDR only"
    from_port   = 22
    to_port     = 22
    protocol    = "tcp"
    cidr_blocks = [var.trusted_ssh_cidr]
  }

  egress {
    description = "Allow all outbound traffic"
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = {
    Name = "${var.project_name}-EC2-SG"
  }
}

# 2. RDS MySQL Security Group
# Allows MySQL (port 3306) inbound strictly and exclusively from the EC2 security group
resource "aws_security_group" "rds_sg" {
  name        = "${var.project_name}-RDS-SG"
  description = "Security group for FoodBridge RDS MySQL database"
  vpc_id      = aws_vpc.foodbridge_vpc.id

  ingress {
    description     = "Allow inbound MySQL access exclusively from EC2 security group"
    from_port       = 3306
    to_port         = 3306
    protocol        = "tcp"
    security_groups = [aws_security_group.ec2_sg.id]
  }

  egress {
    description = "Allow outbound traffic"
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = {
    Name = "${var.project_name}-RDS-SG"
  }
}
