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
  default     = "db.t3.micro"
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
  description = "The master password for the database"
  value       = random_password.master_password.result
  sensitive   = true
}