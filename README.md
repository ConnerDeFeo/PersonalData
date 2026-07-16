# Personal Data Tracker

A tiny serverless REST API for tracking day-by-day personal data (weight, calories,
hours worked, notes, or any other attribute you want) in DynamoDB, fronted by API
Gateway and backed by a single Python Lambda. Provisioned entirely with Terraform.

## Architecture

- **DynamoDB** table `personal-data`: partition key `date` (`YYYY-MM-DD`), one item per
  day, on-demand billing. Attributes are a **fixed schema** — see below.
- **Lambda** (`src/handler.py`, Python 3.12): single function that routes all requests
  internally by HTTP method + path, and enforces the fixed schema for all writes.
- **API Gateway** (REST API): per-method routes on `{proxy+}` — `GET` is public (no key
  required, so the dashboard needs no secret); `POST`/`PUT`/`PATCH`/`DELETE` require an
  `x-api-key` header (API Gateway API key + usage plan).
- **Twilio SMS webhook** (`src/twilio_handler.py`, Python 3.12): a second Lambda behind
  `POST /twilio` on the same API (no API key -- Twilio can't send one; the request is
  instead authenticated via the `X-Twilio-Signature` header). Texting the Twilio number
  something like "worked 8 hours today" calls Claude Haiku on Bedrock, which uses a
  tool to invoke the `records-api` Lambda directly (not over HTTP, so the API key never
  has to be shared with Twilio) to upsert that day's DynamoDB record, then replies via
  SMS (TwiML) with a summary. Relative dates ("today", "yesterday") are resolved
  server-side using the `timezone` Terraform variable.
- **Dashboard** (`frontend/`, React + Vite + TS + Tailwind): a read-only visualization
  of the data, run locally. See "Frontend" below.

## Fixed schema

Only these five numeric attributes may be written to a record, by anyone (HTTP or SMS):
`hours_worked`, `hours_worked_out`, `hours_reading`, `weight`, `calories`. Any other
attribute name, or a non-number value, is rejected with `400`.

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

## Twilio SMS webhook setup (one-time, before deploying)

The Twilio webhook needs a few things Terraform can't provision for you:

1. A Twilio account with a phone number, and its **Auth Token** (Twilio console ->
   Account -> API keys & tokens).
2. **Bedrock model access enabled** for Claude Haiku in your AWS account, in the same
   region as this stack (`us-east-2` by default) -- Bedrock requires an explicit
   per-model access grant in the console before `InvokeModel` will succeed. This can't
   be done via Terraform.
3. The exact **Bedrock model ID** for Claude Haiku available in your account/region --
   verify it against your account's enabled models list in the Bedrock console rather
   than assuming the default in `terraform/variables.tf` (`bedrock_model_id`) is
   correct; update it if it doesn't match.
4. Your **timezone**, if `America/New_York` (the default for `timezone` in
   `terraform/variables.tf`) isn't right -- this is used to resolve "today"/"yesterday"
   in incoming texts.

Create `terraform/terraform.tfvars` (gitignored -- never commit it) with at least:

```hcl
twilio_auth_token   = "your-twilio-auth-token"
allowed_from_number = "+15551234567"                # your phone number, E.164 format
# timezone          = "America/Los_Angeles"          # optional override
# bedrock_model_id  = "anthropic.claude-haiku-..."   # optional override
```

`allowed_from_number` matters: a valid `X-Twilio-Signature` only proves a request came from
Twilio's servers, not that it came from *you* specifically -- anyone who texts your Twilio
number would otherwise be able to trigger it. The webhook rejects any signed request whose
`From` doesn't match this number.

(Alternatively, set `TF_VAR_twilio_auth_token` in your shell instead of a `.tfvars`
file.)

## Deploy

```bash
cd terraform
terraform init
terraform plan
terraform apply
```

Terraform will print `invoke_url`, `api_key_id`, `table_name`, and `twilio_webhook_url`
when it finishes. In the Twilio console, set the phone number's "A message comes in"
webhook to `twilio_webhook_url`, method **HTTP POST**.

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
  -d '{"date":"2026-07-16","weight":175.5,"calories":2200,"hours_worked":8}'
```

**Get a single day** (public, no key needed)
```bash
curl "$API_URL/records/2026-07-16"
```

**List all records** (public, no key needed)
```bash
curl "$API_URL/records"
```

**List records in a date range** (public, no key needed)
```bash
curl "$API_URL/records?start=2026-07-01&end=2026-07-31"
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

**Text the Twilio number**

Once the webhook is configured, just text the number, e.g.:

```
worked 8 hours today
```
```
i worked 8 hours yesterday, forgot to log it
```

You'll get an SMS reply summarizing what was recorded for that date.

## Frontend

Read-only dashboard, run locally against your deployed API.

```bash
cd frontend
cp .env.example .env   # set VITE_API_BASE to your invoke_url
npm install
npm run dev
```

Visualizes: the current week's raw values, an all-time hours split donut, trend lines
for hours worked/weight/calories, all-time weekday averages, and a date picker for any
single day's record. Fetches `GET /records` once (public, no key) and derives
everything client-side.

## Notes

- Writes (`POST`/`PUT`/`PATCH`/`DELETE`) require a valid `x-api-key` header and are
  rejected by API Gateway with 403 before ever reaching the Lambda. `GET` is public.
- Only the five fixed attributes above may be written — any other attribute name, or a
  non-number value, is rejected with 400 (enforced in `src/handler.py`, the single
  choke point for both the HTTP API and the Twilio/SMS path).
- `GET /records` uses a DynamoDB `Scan` (no pagination) — fine at personal-data volumes.
- The Twilio webhook (`POST /twilio`) validates `X-Twilio-Signature` and rejects
  requests that don't come from Twilio with a 403, before any Bedrock or DynamoDB work
  happens.
- To tear everything down: `terraform destroy` from the `terraform/` directory.
