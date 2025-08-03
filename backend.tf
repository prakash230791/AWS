# backend.tf
terraform {
  backend "s3" {
    bucket         = "demo-S3bucket" # <-- TODO: Replace with your S3 bucket name
    key            = "global/s3/terraform.tfstate"
    region         = "us-east-1"
  }
}