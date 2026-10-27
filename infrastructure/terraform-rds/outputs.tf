# ==============================================================================
# FoodBridge RDS Infrastructure - Outputs
# Exposes connection parameters securely without revealing passwords
# ==============================================================================

output "rds_instance_id" {
  description = "The RDS instance identifier"
  value       = aws_db_instance.foodbridge_mysql.id
}

output "rds_instance_arn" {
  description = "The Amazon Resource Name (ARN) of the RDS instance"
  value       = aws_db_instance.foodbridge_mysql.arn
}

output "rds_endpoint" {
  description = "The connection endpoint in host:port format"
  value       = aws_db_instance.foodbridge_mysql.endpoint
}

output "rds_address" {
  description = "The hostname of the RDS database instance"
  value       = aws_db_instance.foodbridge_mysql.address
}

output "rds_port" {
  description = "The database port"
  value       = aws_db_instance.foodbridge_mysql.port
}

output "rds_database_name" {
  description = "The active database / initial schema name"
  value       = aws_db_instance.foodbridge_mysql.db_name
}

output "rds_master_username" {
  description = "The master username for database authentication"
  value       = aws_db_instance.foodbridge_mysql.username
}

output "rds_master_user_secret_arn" {
  description = "The ARN of the AWS Secrets Manager secret holding the auto-generated master password"
  value       = try(aws_db_instance.foodbridge_mysql.master_user_secret[0].secret_arn, null)
}

output "rds_db_subnet_group_name" {
  description = "The name of the DB subnet group used by the database"
  value       = aws_db_subnet_group.foodbridge_db_subnet_group.name
}

output "referenced_vpc_id" {
  description = "The VPC ID housing the RDS instance"
  value       = local.target_vpc_id
}

output "referenced_security_group_id" {
  description = "The Security Group ID protecting MySQL access"
  value       = local.target_rds_sg_id
}
