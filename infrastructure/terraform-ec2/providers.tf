# ==============================================================================
# FoodBridge EC2 Infrastructure - AWS Provider Configuration
# Enforces target account 879385476807 and ap-south-1
# ==============================================================================

provider "aws" {
  region  = var.aws_region
  profile = var.aws_profile != "" ? var.aws_profile : null

  # Strict safety guard: only allow execution against the user's specific account
  allowed_account_ids = [var.aws_account_id]

  default_tags {
    tags = var.default_tags
  }
}
