# Personal Data Tracker

A tiny serverless REST API for tracking day-by-day personal data (weight, calories,
hours worked, notes, or any other attribute you want) in DynamoDB, fronted by API
Gateway and backed by a single Python Lambda. Provisioned entirely with Terraform.

## Architecture

- **DynamoDB** table `personal-data`: partition key `date` (`YYYY-MM-DD`), one item per
  day, on-demand billing. Attributes are dynamic — store whatever you want.
- **Lambda** (`src/handler.py`, Python 3.12): single function that routes all requests
  internally by HTTP method + path.
- **API Gateway** (REST API): a single `ANY /{proxy+}` catch-all forwards everything to
  the Lambda. Every request requires an `x-api-key` header (API Gateway API key + usage
  plan).

## Prerequisites

- AWS credentials configured (`aws configure` or environment variables) with permission
  to create the resources below.
- [Terraform](https://developer.hashicorp.com/terraform) **>= 1.10** (needed for the
  S3 native state-lockfile feature used here).
- AWS CLI (for the one-time bootstrap step and for retrieving the API key value).
- Region: `us-east-2` (Ohio) by default.

## One-time setup: Terraform state bucket

Terraform state is stored remotely in S3. The bucket must exist *before* `terraform init`
because Terraform can't create the backend it's about to use.

```bash
aws s3 mb s3://YOUR-UNIQUE-STATE-BUCKET-NAME --region us-east-2
```

Then edit `terraform/backend.tf` and replace `REPLACE_WITH_YOUR_STATE_BUCKET_NAME` with
the bucket name you just created.

## Deploy

```bash
cd terraform
terraform init
terraform plan
terraform apply
```

Terraform will print `invoke_url`, `api_key_id`, and `table_name` when it finishes.

## Retrieve your API key value

The output only gives you the key's *ID*. Fetch the actual secret value:

```bash
aws apigateway get-api-key --api-key <api_key_id> --include-value --region us-east-2 \
  --query value --output text
```

Save it somewhere safe (e.g. a password manager or local `.env` you don't commit).

## Usage examples

Set these once:

```bash
API_URL="<invoke_url from terraform output>"   # e.g. https://abc123.execute-api.us-east-2.amazonaws.com/prod
API_KEY="<value from the get-api-key command above>"
```

**Create/upsert a record**
```bash
curl -X POST "$API_URL/records" \
  -H "x-api-key: $API_KEY" -H "Content-Type: application/json" \
  -d '{"date":"2026-07-16","weight":175.5,"calories":2200,"hoursWorked":8,"notes":"felt good"}'
```

**Get a single day**
```bash
curl "$API_URL/records/2026-07-16" -H "x-api-key: $API_KEY"
```

**List all records**
```bash
curl "$API_URL/records" -H "x-api-key: $API_KEY"
```

**List records in a date range**
```bash
curl "$API_URL/records?start=2026-07-01&end=2026-07-31" -H "x-api-key: $API_KEY"
```

**Merge/patch specific attributes (leaves others untouched)**
```bash
curl -X PATCH "$API_URL/records/2026-07-16" \
  -H "x-api-key: $API_KEY" -H "Content-Type: application/json" \
  -d '{"weight":174}'
```

**Fully replace a day's attributes**
```bash
curl -X PUT "$API_URL/records/2026-07-16" \
  -H "x-api-key: $API_KEY" -H "Content-Type: application/json" \
  -d '{"weight":174,"calories":2100}'
```

**Remove a single attribute**
```bash
curl -X DELETE "$API_URL/records/2026-07-16/notes" -H "x-api-key: $API_KEY"
```

**Delete an entire day's record**
```bash
curl -X DELETE "$API_URL/records/2026-07-16" -H "x-api-key: $API_KEY"
```

## Notes

- Requests without a valid `x-api-key` header are rejected by API Gateway with 403
  before ever reaching the Lambda.
- Any JSON attribute name/value is accepted — `weight`, `calories`, `hoursWorked`, and
  `notes` are just the ones this project was built around, not a fixed schema.
- `GET /records` uses a DynamoDB `Scan` (no pagination) — fine at personal-data volumes.
- To tear everything down: `terraform destroy` from the `terraform/` directory.
