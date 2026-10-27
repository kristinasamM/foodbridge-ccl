# ==============================================================================
# FoodBridge EC2 Web Application Server (Step 7)
# ==============================================================================

# Single Free Tier / Low-Cost Ubuntu EC2 Instance
resource "aws_instance" "web_server" {
  ami                         = var.ec2_ami_id
  instance_type               = var.instance_type
  subnet_id                   = aws_subnet.public_subnet.id
  vpc_security_group_ids      = [aws_security_group.ec2_sg.id]
  associate_public_ip_address = true

  key_name = var.ssh_key_name != "" ? var.ssh_key_name : null

  # Encrypted Root EBS Block Device (modest 20 GB gp3 storage)
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

  # Automated provisioning script (Gunicorn, Nginx, systemd, Python venv)
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
