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

variable "twilio_auth_token" {
  description = "Twilio Auth Token, used to validate the X-Twilio-Signature header on inbound SMS webhooks. Supply via terraform.tfvars (gitignored) or TF_VAR_twilio_auth_token -- never commit it."
  type        = string
  sensitive   = true
}

variable "timezone" {
  description = "IANA timezone used to resolve relative dates ('today', 'yesterday') in incoming SMS messages"
  type        = string
  default     = "America/New_York"
}

variable "bedrock_model_id" {
  description = "Bedrock model ID for Claude Haiku used by the Twilio SMS webhook. Verify this against the models enabled for your account/region in the Bedrock console before deploying -- it is not validated at plan time."
  type        = string
  default     = "us.anthropic.claude-haiku-4-5-20251001-v1:0"
}
