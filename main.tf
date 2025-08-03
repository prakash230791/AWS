terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

# Configure the AWS Provider
provider "aws" {
  region = "us-east-1" # Or your preferred region
}

# Create a globally unique S3 bucket name
# Note: For a real project, you might use a random suffix or a dedicated naming module.
data "aws_caller_identity" "current" {}
data "aws_region" "current" {}

resource "aws_s3_bucket" "my_secure_bucket" {
  bucket = "my-secure-bucket-${data.aws_caller_identity.current.account_id}-${data.aws_region.current.name}"
}

resource "aws_s3_bucket_public_access_block" "my_secure_bucket_pab" {
  bucket = aws_s3_bucket.my_secure_bucket.id

  block_public_acls   = true
  block_public_policy = true
  ignore_public_acls  = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_versioning" "my_secure_bucket_versioning" {
  bucket = aws_s3_bucket.my_secure_bucket.id
  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "my_secure_bucket_sse" {
  bucket = aws_s3_bucket.my_secure_bucket.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm     = "AES256"
    }
  }
}
