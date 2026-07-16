# Twilio SMS webhook: texting the number a message like "worked 8 hours
# today" invokes Claude Haiku on Bedrock, which calls back into the
# records-api Lambda (directly, via lambda:InvokeFunction -- not over HTTPS
# with the API key, so the key never has to be shared with Twilio) to update
# that day's DynamoDB record, then replies via TwiML with a summary.
#
# Reuses data.archive_file.lambda_zip (declared in lambda.tf) since it
# already zips the whole ../src directory, including src/twilio_handler.py.

resource "aws_lambda_function" "twilio_webhook" {
  function_name    = "${var.project_name}-twilio-webhook"
  role             = aws_iam_role.twilio_webhook_exec.arn
  handler          = "twilio_handler.lambda_handler"
  runtime          = "python3.12"
  filename         = data.archive_file.lambda_zip.output_path
  source_code_hash = data.archive_file.lambda_zip.output_base64sha256
  timeout          = 30 # headroom for the Bedrock round trip(s)
  memory_size      = 128

  environment {
    variables = {
      RECORDS_API_FUNCTION_NAME = aws_lambda_function.records_api.function_name
      BEDROCK_MODEL_ID          = var.bedrock_model_id
      TWILIO_AUTH_TOKEN         = var.twilio_auth_token
      TIMEZONE                  = var.timezone
    }
  }

  tags = var.tags
}

resource "aws_lambda_permission" "apigw_invoke_twilio" {
  statement_id  = "AllowAPIGatewayInvokeTwilio"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.twilio_webhook.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_api_gateway_rest_api.records_api.execution_arn}/*/*"
}

# Dedicated role (rather than extending lambda_exec) so the CRUD Lambda
# doesn't gain Bedrock/invoke-function permissions it doesn't need, and vice
# versa.
data "aws_iam_policy_document" "twilio_webhook_assume_role" {
  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["lambda.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "twilio_webhook_exec" {
  name               = "${var.project_name}-twilio-webhook-exec"
  assume_role_policy = data.aws_iam_policy_document.twilio_webhook_assume_role.json
  tags               = var.tags
}

resource "aws_iam_role_policy_attachment" "twilio_webhook_basic_execution" {
  role       = aws_iam_role.twilio_webhook_exec.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
}

# Scoped to the configured model plus any inference profile in this account
# (some Bedrock Claude models are only invocable via a cross-region
# inference-profile ARN rather than the bare foundation-model ARN).
data "aws_iam_policy_document" "bedrock_invoke" {
  statement {
    effect  = "Allow"
    actions = ["bedrock:InvokeModel"]
    resources = [
      "arn:aws:bedrock:${var.aws_region}::foundation-model/${var.bedrock_model_id}",
      "arn:aws:bedrock:${var.aws_region}:*:inference-profile/*",
    ]
  }
}

resource "aws_iam_role_policy" "bedrock_invoke" {
  name   = "${var.project_name}-bedrock-invoke"
  role   = aws_iam_role.twilio_webhook_exec.id
  policy = data.aws_iam_policy_document.bedrock_invoke.json
}

data "aws_iam_policy_document" "invoke_records_api" {
  statement {
    effect    = "Allow"
    actions   = ["lambda:InvokeFunction"]
    resources = [aws_lambda_function.records_api.arn]
  }
}

resource "aws_iam_role_policy" "invoke_records_api" {
  name   = "${var.project_name}-invoke-records-api"
  role   = aws_iam_role.twilio_webhook_exec.id
  policy = data.aws_iam_policy_document.invoke_records_api.json
}
