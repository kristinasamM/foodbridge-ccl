# ==============================================================================
# FoodBridge EC2 Web Application Server (Step 7A)
# Targeted exclusively for AWS Account: 879385476807 in ap-south-1
# Attaches to existing manually created VPC, Public Subnet, and EC2 Security Group
# ==============================================================================

resource "aws_instance" "web_server" {
  ami                         = local.target_ami_id
  instance_type               = var.instance_type
  subnet_id                   = local.target_subnet_id
  vpc_security_group_ids      = [local.target_sg_id]
  associate_public_ip_address = true

  key_name = var.ssh_key_name != "" ? var.ssh_key_name : null

  # Encrypted 20 GB gp3 root EBS volume (modest, Free Tier eligible)
  root_block_device {
    volume_size           = var.root_volume_size
    volume_type           = "gp3"
    encrypted             = true
    delete_on_termination = true

    tags = merge(
      var.default_tags,
      {
        Name = "${var.project_name}-Web-Server-Root-Disk"
      }
    )
  }

  # Automated bootstrap script: Ubuntu packages, Python venv, Gunicorn, systemd, Nginx, SECRET_KEY
  user_data                   = file("${path.module}/user_data.sh")
  user_data_replace_on_change = false

  tags = merge(
    var.default_tags,
    {
      Name = "${var.project_name}-Web-Server"
      Role = "WebServer"
    }
  )
}
