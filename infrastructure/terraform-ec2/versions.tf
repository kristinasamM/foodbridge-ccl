# ==============================================================================
# FoodBridge EC2 Infrastructure - Terraform & Provider Versions
# Dedicated for AWS Account: 879385476807 (ap-south-1)
# ==============================================================================

terraform {
  required_version = ">= 1.5.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}
