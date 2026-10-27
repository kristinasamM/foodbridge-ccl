# ==============================================================================
# FoodBridge EC2 Infrastructure - Outputs
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
  description = "Public DNS hostname of the FoodBridge EC2 web server"
  value       = aws_instance.web_server.public_dns
}

output "ec2_app_url" {
  description = "HTTP URL to access the deployed FoodBridge web application in a browser"
  value       = "http://${aws_instance.web_server.public_ip}"
}

output "ec2_ssh_command" {
  description = "SSH command template to connect to the EC2 instance"
  value       = var.ssh_key_name != "" ? "ssh -i <path-to-${var.ssh_key_name}.pem> ubuntu@${aws_instance.web_server.public_ip}" : "ssh ubuntu@${aws_instance.web_server.public_ip}"
}

output "referenced_vpc_id" {
  description = "ID of the referenced VPC"
  value       = data.aws_vpc.existing_vpc.id
}

output "referenced_subnet_id" {
  description = "ID of the referenced Public Subnet where EC2 was deployed"
  value       = local.target_subnet_id
}

output "referenced_security_group_id" {
  description = "ID of the referenced EC2 Security Group protecting the instance"
  value       = local.target_sg_id
}
