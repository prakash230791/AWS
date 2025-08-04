terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.0"
    }
    tls = {
      source = "hashicorp/tls"
      version = "~> 4.0"
    }
    local = {
      source = "hashicorp/local"
      version = "~> 2.2"
    }
  }
}

provider "aws" {
  region = "us-east-1" # Specify your desired AWS region
}

# ----------------------------------------------------------------------------------------------------------------------
# DATA SOURCES
# ----------------------------------------------------------------------------------------------------------------------

data "http" "my_ip" {
  url = "https://ipv4.icanhazip.com"
}

# ----------------------------------------------------------------------------------------------------------------------
# NETWORKING RESOURCES
# ----------------------------------------------------------------------------------------------------------------------

resource "aws_vpc" "main" {
  cidr_block = "10.0.0.0/16"

  tags = {
    Name = "main-vpc"
  }
}

resource "aws_subnet" "main_a" {
  vpc_id            = aws_vpc.main.id
  cidr_block        = "10.0.1.0/24"
  availability_zone = "us-east-1a"

  tags = {
    Name = "main-subnet-a"
  }
}

resource "aws_subnet" "main_b" {
  vpc_id            = aws_vpc.main.id
  cidr_block        = "10.0.2.0/24"
  availability_zone = "us-east-1b"

  tags = {
    Name = "main-subnet-b"
  }
}

resource "aws_internet_gateway" "gw" {
  vpc_id = aws_vpc.main.id

  tags = {
    Name = "main-igw"
  }
}

resource "aws_route_table" "rt" {
  vpc_id = aws_vpc.main.id

  route {
    cidr_block = "0.0.0.0/0"
    gateway_id = aws_internet_gateway.gw.id
  }

  tags = {
    Name = "main-rt"
  }
}

resource "aws_route_table_association" "a" {
  subnet_id      = aws_subnet.main_a.id
  route_table_id = aws_route_table.rt.id
}

resource "aws_route_table_association" "b" {
  subnet_id      = aws_subnet.main_b.id
  route_table_id = aws_route_table.rt.id
}

# ----------------------------------------------------------------------------------------------------------------------
# SSH KEY RESOURCES
# ----------------------------------------------------------------------------------------------------------------------

resource "tls_private_key" "ssh_key" {
  algorithm = "RSA"
  rsa_bits  = 4096
}

resource "aws_key_pair" "ssh_key_pair" {
  key_name   = "my-ssh-key"
  public_key = tls_private_key.ssh_key.public_key_openssh
}

resource "local_file" "private_key_pem" {
  content  = tls_private_key.ssh_key.private_key_pem
  filename = "my-ssh-key.pem"
}


# ----------------------------------------------------------------------------------------------------------------------
# DATABASE VARIABLES
# ----------------------------------------------------------------------------------------------------------------------

variable "db_name" {
  description = "The name of the database to create"
  type        = string
  default     = "oracledb"
}

variable "db_username" {
  description = "The master username for the database"
  type        = string
  default     = "admin"
}

variable "instance_class" {
  description = "The instance class for the RDS instance"
  type        = string
  default     = "db.t3.small"
}

variable "allocated_storage" {
  description = "The allocated storage in gigabytes"
  type        = number
  default     = 20
}

variable "enable_rds" {
  description = "Set to true to enable RDS deployment, false to disable"
  type        = bool
  default     = true
}

# ----------------------------------------------------------------------------------------------------------------------
# DATABASE RESOURCES
# ----------------------------------------------------------------------------------------------------------------------

resource "random_password" "master_password" {
  count            = var.enable_rds ? 1 : 0
  length           = 16
  special          = true
  override_special = "!#$%&'()*+,-./:;<=>?@[]^_`{|}~"
}

resource "aws_security_group" "rds_sg" {
  count       = var.enable_rds ? 1 : 0
  name        = "rds-oracle-sg"
  description = "Security group for Oracle RDS"
  vpc_id      = aws_vpc.main.id

  ingress {
    from_port   = 1521
    to_port     = 1521
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"] # WARNING: This allows access from any IP. Restrict this to your IP range in a production environment.
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = {
    Name = "rds-oracle-sg"
  }
}

resource "aws_db_subnet_group" "rds_subnet_group" {
  count      = var.enable_rds ? 1 : 0
  name       = "rds-oracle-subnet-group"
  subnet_ids = [aws_subnet.main_a.id, aws_subnet.main_b.id]

  tags = {
    Name = "RDS Oracle Subnet Group"
  }
}

resource "aws_db_instance" "oracle_rds" {
  count                = var.enable_rds ? 1 : 0
  allocated_storage    = var.allocated_storage
  storage_type         = "gp2"
  engine               = "oracle-se2" # Or "oracle-ee", "oracle-se2-cdb", "oracle-ee-cdb"
  engine_version       = "19.0.0.0.ru-2022-01.rur-2022-01.r1" # Specify your desired engine version
  instance_class       = var.instance_class
  db_name              = var.db_name
  username             = var.db_username
  password             = random_password.master_password[0].result
  db_subnet_group_name = aws_db_subnet_group.rds_subnet_group[0].name
  vpc_security_group_ids = [aws_security_group.rds_sg[0].id]
  license_model        = "license-included" # Or "bring-your-own-license"
  skip_final_snapshot  = true

  tags = {
    Name = "oracle-rds-instance"
  }
}

resource "random_string" "secret_suffix" {
  count   = var.enable_rds ? 1 : 0
  length  = 8
  special = false
  upper   = false
}

resource "aws_secretsmanager_secret" "oracle_rds_password" {
  count       = var.enable_rds ? 1 : 0
  name        = "oracle-rds-master-password-${random_string.secret_suffix[0].result}"
  description = "Master password for the Oracle RDS instance" 
}

resource "aws_secretsmanager_secret_version" "oracle_rds_password_version" {
  count         = var.enable_rds ? 1 : 0
  secret_id     = aws_secretsmanager_secret.oracle_rds_password[0].id
  secret_string = random_password.master_password[0].result
}

# ----------------------------------------------------------------------------------------------------------------------
# EC2 INSTANCE RESOURCES
# ----------------------------------------------------------------------------------------------------------------------

variable "ec2_ami_id" {
  description = "The AMI ID for the EC2 instance (e.g., Amazon Linux 2)"
  type        = string
  default     = "ami-0922553b7b0369273" # Example: Amazon Linux 2 AMI for us-east-1 (Updated)
}

resource "aws_security_group" "ec2_sg" {
  name        = "ec2-jump-sg"
  description = "Security group for EC2 jump host"
  vpc_id      = aws_vpc.main.id

  ingress {
    from_port   = 22
    to_port     = 22
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"] # WARNING: Restrict this to your IP for production
  }

  # Allow outbound to RDS
  egress {
    from_port   = 1521
    to_port     = 1521
    protocol    = "tcp"
    security_groups = var.enable_rds ? [aws_security_group.rds_sg[0].id] : [] # Conditional access
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"] # Allow all outbound for general use
  }

  tags = {
    Name = "ec2-jump-sg"
  }
}

resource "aws_instance" "jump_host" {
  ami                    = var.ec2_ami_id
  instance_type          = "t3.micro" # Free tier eligible, supports UEFI
  subnet_id              = aws_subnet.main_a.id # Place in one of the subnets
  vpc_security_group_ids = [aws_security_group.ec2_sg.id]
  key_name               = aws_key_pair.ssh_key_pair.key_name
  associate_public_ip_address = true # Assign a public IP for SSH access

  tags = {
    Name = "Oracle-RDS-Jump-Host"
  }
}

# ----------------------------------------------------------------------------------------------------------------------
# OUTPUTS
# ----------------------------------------------------------------------------------------------------------------------

output "rds_endpoint" {
  description = "The endpoint of the RDS instance"
  value       = var.enable_rds ? aws_db_instance.oracle_rds[0].endpoint : "RDS not deployed"
}

output "rds_port" {
  description = "The port of the RDS instance"
  value       = var.enable_rds ? aws_db_instance.oracle_rds[0].port : "RDS not deployed"
}

output "db_master_password" {
  description = "The master password for the database (stored in Secrets Manager)"
  value       = var.enable_rds ? aws_secretsmanager_secret.oracle_rds_password[0].arn : "RDS not deployed"
}

output "secrets_manager_secret_arn" {
  description = "ARN of the Secrets Manager secret storing the RDS master password"
  value       = var.enable_rds ? aws_secretsmanager_secret.oracle_rds_password[0].arn : "RDS not deployed"
}

output "ec2_public_ip" {
  description = "The public IP address of the EC2 jump host"
  value       = aws_instance.jump_host.public_ip
}

output "ec2_private_ip" {
  description = "The private IP address of the EC2 jump host"
  value       = aws_instance.jump_host.private_ip
}

output "private_key_pem" {
  description = "The private key to SSH into the EC2 instance"
  value       = tls_private_key.ssh_key.private_key_pem
  sensitive   = true
}