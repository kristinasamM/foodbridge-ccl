# ==============================================================================
# FoodBridge RDS Infrastructure - Main Resources
# Dedicated module for AWS Account: 879385476807 (ap-south-1)
# ==============================================================================

# ------------------------------------------------------------------------------
# 1. RDS DB Subnet Group (Spans 2 Private Subnets in ap-south-1a and ap-south-1b)
# ------------------------------------------------------------------------------
resource "aws_db_subnet_group" "foodbridge_db_subnet_group" {
  name        = "${lower(var.project_name)}-db-subnet-group"
  description = "FoodBridge isolated private DB subnet group across AZs"
  subnet_ids  = local.target_subnet_ids

  tags = merge(
    var.default_tags,
    {
      Name = "${var.project_name}-DB-Subnet-Group"
      Role = "DatabaseSubnetGroup"
    }
  )
}

# ------------------------------------------------------------------------------
# 2. Low-Cost RDS MySQL 8.0 Instance
# ------------------------------------------------------------------------------
resource "aws_db_instance" "foodbridge_mysql" {
  identifier        = var.db_identifier
  db_name           = var.db_name
  engine            = "mysql"
  engine_version    = var.engine_version
  instance_class    = var.instance_class
  allocated_storage = var.allocated_storage
  storage_type      = var.storage_type

  # Master administrative user
  username = var.db_username

  # AWS Secrets Manager integration:
  # Generates and manages the master password securely in AWS Secrets Manager.
  # Prevents hardcoding and eliminates plaintext passwords from Terraform state.
  manage_master_user_password = true

  # Networking and Security
  db_subnet_group_name   = aws_db_subnet_group.foodbridge_db_subnet_group.name
  vpc_security_group_ids = [local.target_rds_sg_id]
  publicly_accessible    = false
  port                   = 3306

  # Cost Optimization & Strict Resource Controls
  multi_az                     = false # Single-AZ to avoid doubling compute/storage costs
  max_allocated_storage        = 0     # Strictly disable storage autoscaling to prevent surprise charges
  performance_insights_enabled = false # Disable to avoid any non-free tier insights telemetry
  monitoring_interval          = 0     # Disable enhanced monitoring daemon

  # Safety, Backup & Snapshot Policies
  deletion_protection       = true  # Prevent accidental console or CLI deletion
  skip_final_snapshot       = false # Require a final snapshot before deletion
  final_snapshot_identifier = "${var.db_identifier}-final-snapshot"
  backup_retention_period   = var.backup_retention_period
  backup_window             = "20:00-20:30"
  maintenance_window        = "Mon:00:00-Mon:00:30"

  # Lifecycle Controls
  auto_minor_version_upgrade  = true
  allow_major_version_upgrade = false
  apply_immediately           = true

  tags = merge(
    var.default_tags,
    {
      Name = "${var.project_name}-MySQL-DB"
      Role = "Database"
    }
  )
}
