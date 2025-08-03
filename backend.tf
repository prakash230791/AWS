# backend.tf
terraform {
  backend "s3" {
    bucket         = "tfstate-979858933388-us-east-1" # <-- TODO: Replace with your S3 bucket name
    key            = "global/s3/terraform.tfstate"
    region         = "us-east-1"
  }
}