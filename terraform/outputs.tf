output "invoke_url" {
  description = "Base URL to call the API (append /records ...)"
  value       = aws_api_gateway_stage.records_api.invoke_url
}

output "table_name" {
  description = "Name of the DynamoDB table"
  value       = aws_dynamodb_table.personal_data.name
}

output "twilio_webhook_url" {
  description = "URL to configure as the Twilio phone number's 'A message comes in' webhook (HTTP POST)"
  value       = "${aws_api_gateway_stage.records_api.invoke_url}/twilio"
}
