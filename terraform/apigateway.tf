# Single greedy proxy: API Gateway forwards every method/path under the API
# to the Lambda, which does its own routing (see src/handler.py). This keeps
# route knowledge in one place instead of duplicating it in Terraform.
resource "aws_api_gateway_rest_api" "records_api" {
  name = "${var.project_name}-api"
  tags = var.tags
}

resource "aws_api_gateway_resource" "proxy" {
  rest_api_id = aws_api_gateway_rest_api.records_api.id
  parent_id   = aws_api_gateway_rest_api.records_api.root_resource_id
  path_part   = "{proxy+}"
}

# GET only, public -- writes aren't exposed over HTTP at all. The only way to
# add/edit data is via SMS (twilio_handler.py invokes this Lambda directly,
# bypassing API Gateway -- see its module docstring).
resource "aws_api_gateway_method" "proxy_get" {
  rest_api_id      = aws_api_gateway_rest_api.records_api.id
  resource_id      = aws_api_gateway_resource.proxy.id
  http_method      = "GET"
  authorization    = "NONE"
  api_key_required = false

  request_parameters = {
    "method.request.path.proxy" = true
  }
}

resource "aws_api_gateway_integration" "proxy_get" {
  rest_api_id             = aws_api_gateway_rest_api.records_api.id
  resource_id             = aws_api_gateway_resource.proxy.id
  http_method             = aws_api_gateway_method.proxy_get.http_method
  integration_http_method = "POST" # Lambda proxy integrations are always invoked via POST
  type                    = "AWS_PROXY"
  uri                     = aws_lambda_function.records_api.invoke_arn
}

# GET on the root resource ("/") so the API doesn't 403/404 confusingly if
# someone hits the base URL directly. Not part of the documented contract.
resource "aws_api_gateway_method" "root_get" {
  rest_api_id      = aws_api_gateway_rest_api.records_api.id
  resource_id      = aws_api_gateway_rest_api.records_api.root_resource_id
  http_method      = "GET"
  authorization    = "NONE"
  api_key_required = false
}

resource "aws_api_gateway_integration" "root_get" {
  rest_api_id             = aws_api_gateway_rest_api.records_api.id
  resource_id             = aws_api_gateway_rest_api.records_api.root_resource_id
  http_method             = aws_api_gateway_method.root_get.http_method
  integration_http_method = "POST"
  type                    = "AWS_PROXY"
  uri                     = aws_lambda_function.records_api.invoke_arn
}

# Twilio's inbound-SMS webhook -- the only path that can write data. Twilio
# can't send an x-api-key header, so this route has none; authenticity is
# enforced inside the Lambda via X-Twilio-Signature + sender-number checks.
resource "aws_api_gateway_resource" "twilio" {
  rest_api_id = aws_api_gateway_rest_api.records_api.id
  parent_id   = aws_api_gateway_rest_api.records_api.root_resource_id
  path_part   = "twilio"
}

resource "aws_api_gateway_method" "twilio_post" {
  rest_api_id      = aws_api_gateway_rest_api.records_api.id
  resource_id      = aws_api_gateway_resource.twilio.id
  http_method      = "POST"
  authorization    = "NONE"
  api_key_required = false
}

resource "aws_api_gateway_integration" "twilio_post" {
  rest_api_id             = aws_api_gateway_rest_api.records_api.id
  resource_id             = aws_api_gateway_resource.twilio.id
  http_method             = aws_api_gateway_method.twilio_post.http_method
  integration_http_method = "POST"
  type                    = "AWS_PROXY"
  uri                     = aws_lambda_function.twilio_webhook.invoke_arn
}

resource "aws_api_gateway_deployment" "records_api" {
  rest_api_id = aws_api_gateway_rest_api.records_api.id

  triggers = {
    redeployment = sha1(jsonencode([
      aws_api_gateway_resource.proxy.id,
      aws_api_gateway_method.proxy_get.id,
      aws_api_gateway_integration.proxy_get.id,
      aws_api_gateway_method.root_get.id,
      aws_api_gateway_integration.root_get.id,
      aws_api_gateway_resource.twilio.id,
      aws_api_gateway_method.twilio_post.id,
      aws_api_gateway_integration.twilio_post.id,
    ]))
  }

  lifecycle {
    create_before_destroy = true
  }

  depends_on = [
    aws_api_gateway_integration.proxy_get,
    aws_api_gateway_integration.root_get,
    aws_api_gateway_integration.twilio_post,
  ]
}

resource "aws_api_gateway_stage" "records_api" {
  deployment_id = aws_api_gateway_deployment.records_api.id
  rest_api_id   = aws_api_gateway_rest_api.records_api.id
  stage_name    = var.stage_name
  tags          = var.tags
}
