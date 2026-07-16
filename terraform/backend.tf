# Remote state in S3. The bucket must already exist before `terraform init`
# (see README for the one-time bootstrap command). Uses Terraform's native
# S3 lockfile (use_lockfile), which requires Terraform >= 1.10 -- no separate
# DynamoDB lock table needed.
terraform {
  backend "s3" {
    bucket       = "personal-data-tf-state"
    key          = "personal-data-backend/terraform.tfstate"
    region       = "us-east-2"
    use_lockfile = true
    encrypt      = true
  }
}
