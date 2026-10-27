# ==============================================================================
# FoodBridge Infrastructure Outputs
# ==============================================================================

output "vpc_id" {
  description = "ID of the FoodBridge VPC"
  value       = aws_vpc.foodbridge_vpc.id
}

output "vpc_cidr" {
  description = "CIDR block of the FoodBridge VPC"
  value       = aws_vpc.foodbridge_vpc.cidr_block
}

output "internet_gateway_id" {
  description = "ID of the Internet Gateway attached to the VPC"
  value       = aws_internet_gateway.igw.id
}

output "public_subnet_id" {
  description = "ID of the public subnet (for EC2 web server)"
  value       = aws_subnet.public_subnet.id
}

output "public_subnet_az" {
  description = "Availability zone of the public subnet"
  value       = aws_subnet.public_subnet.availability_zone
}

output "private_subnet_a_id" {
  description = "ID of Private Subnet A"
  value       = aws_subnet.private_subnet_a.id
}

output "private_subnet_a_az" {
  description = "Availability zone of Private Subnet A"
  value       = aws_subnet.private_subnet_a.availability_zone
}

output "private_subnet_b_id" {
  description = "ID of Private Subnet B"
  value       = aws_subnet.private_subnet_b.id
}

output "private_subnet_b_az" {
  description = "Availability zone of Private Subnet B"
  value       = aws_subnet.private_subnet_b.availability_zone
}

output "public_route_table_id" {
  description = "ID of the public route table"
  value       = aws_route_table.public_rt.id
}

output "private_route_table_id" {
  description = "ID of the private route table"
  value       = aws_route_table.private_rt.id
}

output "ec2_security_group_id" {
  description = "ID of the EC2 security group"
  value       = aws_security_group.ec2_sg.id
}

output "rds_security_group_id" {
  description = "ID of the RDS MySQL security group"
  value       = aws_security_group.rds_sg.id
}

# ==============================================================================
# EC2 Outputs (Step 7)
# ==============================================================================

output "ec2_instance_id" {
  description = "ID of the deployed FoodBridge EC2 instance"
  value       = aws_instance.web_server.id
}

output "ec2_public_ip" {
  description = "Public IPv4 address of the FoodBridge EC2 web server"
  value       = aws_instance.web_server.public_ip
}

output "ec2_public_dns" {
  description = "Public DNS name of the FoodBridge EC2 web server"
  value       = aws_instance.web_server.public_dns
}

output "ec2_app_url" {
  description = "HTTP URL to access the deployed FoodBridge web application"
  value       = "http://${aws_instance.web_server.public_ip}"
}

output "ec2_ssh_command" {
  description = "Command template for connecting to the EC2 instance via SSH"
  value       = "ssh -i <your-key.pem> ubuntu@${aws_instance.web_server.public_ip}"
}
