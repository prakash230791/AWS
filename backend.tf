# backend.tf
terraform {
  backend "s3" {
    bucket         = "your-terraform-state-bucket-name" # <-- TODO: Replace with your S3 bucket name
    key            = "global/s3/terraform.tfstate"
    region         = "us-east-1"
    dynamodb_table = "your-terraform-lock-table-name" # <-- TODO: Replace with your DynamoDB table name
  }
}