variable "aws_region" {
  description = "AWS region to deploy into"
  type        = string
  default     = "us-east-2"
}

variable "project_name" {
  description = "Prefix used for naming resources"
  type        = string
  default     = "personal-data"
}

variable "table_name" {
  description = "Name of the DynamoDB table"
  type        = string
  default     = "personal-data"
}

variable "stage_name" {
  description = "API Gateway deployment stage name"
  type        = string
  default     = "prod"
}

variable "tags" {
  description = "Common tags applied to all resources"
  type        = map(string)
  default = {
    Project = "personal-data-tracker"
  }
}
