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
  }
}

provider "aws" {
  region = "us-east-1" # Specify your desired AWS region
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

# ----------------------------------------------------------------------------------------------------------------------
# DATABASE RESOURCES
# ----------------------------------------------------------------------------------------------------------------------

resource "random_password" "master_password" {
  length           = 16
  special          = true
  override_special = "!#$%&'()*+,-./:;<=>?@[]^_`{|}~"
}

resource "aws_security_group" "rds_sg" {
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
  name       = "rds-oracle-subnet-group"
  subnet_ids = [aws_subnet.main_a.id, aws_subnet.main_b.id]

  tags = {
    Name = "RDS Oracle Subnet Group"
  }
}

resource "aws_db_instance" "oracle_rds" {
  allocated_storage    = var.allocated_storage
  storage_type         = "gp2"
  engine               = "oracle-se2" # Or "oracle-ee", "oracle-se2-cdb", "oracle-ee-cdb"
  engine_version       = "19.0.0.0.ru-2022-01.rur-2022-01.r1" # Specify your desired engine version
  instance_class       = var.instance_class
  db_name              = var.db_name
  username             = var.db_username
  password             = random_password.master_password.result
  db_subnet_group_name = aws_db_subnet_group.rds_subnet_group.name
  vpc_security_group_ids = [aws_security_group.rds_sg.id]
  license_model        = "license-included" # Or "bring-your-own-license"
  skip_final_snapshot  = true

  tags = {
    Name = "oracle-rds-instance"
  }
}

resource "aws_secretsmanager_secret" "oracle_rds_password" {
  name        = "oracle-rds-master-password"
  description = "Master password for the Oracle RDS instance"
}

resource "aws_secretsmanager_secret_version" "oracle_rds_password_version" {
  secret_id     = aws_secretsmanager_secret.oracle_rds_password.id
  secret_string = random_password.master_password.result
}

# ----------------------------------------------------------------------------------------------------------------------
# EC2 INSTANCE RESOURCES
# ----------------------------------------------------------------------------------------------------------------------

variable "ec2_ami_id" {
  description = "The AMI ID for the EC2 instance (e.g., Amazon Linux 2)"
  type        = string
  default     = "ami-053b04d48d167755a" # Example: Amazon Linux 2 AMI for us-east-1
}

variable "ec2_key_pair_name" {
  description = "The name of the EC2 Key Pair for SSH access"
  type        = string
  # IMPORTANT: Replace with your actual key pair name
  # default     = "my-ssh-key"
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
    security_groups = [aws_security_group.rds_sg.id]
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
  instance_type          = "t2.micro" # Free tier eligible
  subnet_id              = aws_subnet.main_a.id # Place in one of the subnets
  vpc_security_group_ids = [aws_security_group.ec2_sg.id]
  key_name               = var.ec2_key_pair_name
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
  value       = aws_db_instance.oracle_rds.endpoint
}

output "rds_port" {
  description = "The port of the RDS instance"
  value       = aws_db_instance.oracle_rds.port
}

output "db_master_password" {
  description = "The master password for the database (stored in Secrets Manager)"
  value       = aws_secretsmanager_secret.oracle_rds_password.arn
}

output "secrets_manager_secret_arn" {
  description = "ARN of the Secrets Manager secret storing the RDS master password"
  value       = aws_secretsmanager_secret.oracle_rds_password.arn
}

output "ec2_public_ip" {
  description = "The public IP address of the EC2 jump host"
  value       = aws_instance.jump_host.public_ip
}

output "ec2_private_ip" {
  description = "The private IP address of the EC2 jump host"
  value       = aws_instance.jump_host.private_ip
}