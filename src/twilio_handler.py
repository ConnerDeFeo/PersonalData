"""
Twilio SMS webhook -- Bedrock Claude Haiku -- records-api Lambda.

Twilio POSTs an application/x-www-form-urlencoded body to this Lambda via API
Gateway (POST /twilio -> AWS_PROXY). The flow:

  1. Validate the X-Twilio-Signature header (HMAC-SHA1 over the full request
     URL + sorted form params, per Twilio's documented algorithm) using
     TWILIO_AUTH_TOKEN. Requests that don't validate are rejected before any
     Bedrock/DynamoDB work happens.
  2. Resolve "today" in the TIMEZONE env var and ask Claude Haiku (via
     Bedrock's raw InvokeModel API -- no anthropic SDK dependency, since this
     project has no dependency-packaging step) to turn the SMS body into a
     call to the update_day_record tool.
  3. Execute update_day_record by invoking the records-api Lambda directly
     (boto3 lambda:InvokeFunction with a synthetic API Gateway proxy event),
     reusing handler.py's existing validation/PATCH logic instead of
     duplicating it or looping back through API Gateway with the API key.
  4. Send the tool result back to Claude for a short natural-language
     summary, and reply to the SMS with that summary as TwiML.

Twilio's inbound webhook body is form-encoded, not JSON -- this does not
reuse handler.py's _parse_body, which assumes a JSON body.
"""

import base64
import hashlib
import hmac
import json
import os
from datetime import datetime
from urllib.parse import parse_qsl
from zoneinfo import ZoneInfo

import boto3

bedrock = boto3.client("bedrock-runtime")
lambda_client = boto3.client("lambda")

BEDROCK_MODEL_ID = os.environ["BEDROCK_MODEL_ID"]
RECORDS_API_FUNCTION_NAME = os.environ["RECORDS_API_FUNCTION_NAME"]
TWILIO_AUTH_TOKEN = os.environ["TWILIO_AUTH_TOKEN"]
TIMEZONE = os.environ["TIMEZONE"]

UPDATE_TOOL = {
    "name": "update_day_record",
    "description": (
        "Create or update the attributes recorded for a single calendar day. "
        "Only call this once you have determined the exact date (YYYY-MM-DD) "
        "the message refers to and the attribute(s) to record."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "date": {
                "type": "string",
                "description": "The date the record applies to, in YYYY-MM-DD format.",
            },
            "attributes": {
                "type": "object",
                "description": (
                    "Attributes to set on that day's record, e.g. "
                    '{"hoursWorked": 8}. Merged into any existing record for '
                    "that date -- existing attributes not mentioned are left "
                    "untouched."
                ),
            },
        },
        "required": ["date", "attributes"],
    },
}


class TwilioAuthError(Exception):
    """Raised when the X-Twilio-Signature header doesn't validate."""


# ---------------------------------------------------------------------------
# Twilio request parsing / signature validation
# ---------------------------------------------------------------------------

def _get_header(event, name):
    headers = event.get("headers") or {}
    name_lower = name.lower()
    for key, value in headers.items():
        if key.lower() == name_lower:
            return value
    return None


def _parse_form_body(event):
    raw = event.get("body") or ""
    if event.get("isBase64Encoded"):
        raw = base64.b64decode(raw).decode("utf-8")
    return dict(parse_qsl(raw, keep_blank_values=True))


def _request_url(event):
    """Reconstruct the exact HTTPS URL Twilio signed, from an API Gateway
    REST API (v1) Lambda-proxy event. event['path'] is the resource path
    without the stage (e.g. '/twilio'); the stage must be prepended to match
    the URL Twilio actually POSTed to.
    """
    host = _get_header(event, "Host")
    stage = (event.get("requestContext") or {}).get("stage", "")
    path = event.get("path", "")
    return f"https://{host}/{stage}{path}"


def _validate_twilio_signature(url, params, signature):
    """Twilio's request-validation algorithm: HMAC-SHA1 of the full request
    URL with all POST params' key+value pairs appended (sorted by key,
    concatenated with no separator), base64-encoded, compared to the header.
    https://www.twilio.com/docs/usage/webhooks/webhook-security
    """
    data = url
    for key in sorted(params):
        data += key + params[key]
    computed = base64.b64encode(
        hmac.new(TWILIO_AUTH_TOKEN.encode("utf-8"), data.encode("utf-8"), hashlib.sha1).digest()
    ).decode("utf-8")
    if not signature or not hmac.compare_digest(computed, signature):
        raise TwilioAuthError("Invalid X-Twilio-Signature")


def _xml_escape(text):
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _twiml_response(status, message):
    body = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        f"<Response><Message>{_xml_escape(message)}</Message></Response>"
    )
    return {
        "statusCode": status,
        "headers": {"Content-Type": "application/xml"},
        "body": body,
    }


# ---------------------------------------------------------------------------
# records-api invocation (direct Lambda-to-Lambda, bypasses API Gateway/key)
# ---------------------------------------------------------------------------

def _invoke_records_api(method, path, body_dict=None):
    proxy_event = {
        "httpMethod": method,
        "path": path,
        "queryStringParameters": None,
        "body": json.dumps(body_dict) if body_dict is not None else None,
    }
    response = lambda_client.invoke(
        FunctionName=RECORDS_API_FUNCTION_NAME,
        InvocationType="RequestResponse",
        Payload=json.dumps(proxy_event).encode("utf-8"),
    )
    if response.get("FunctionError"):
        raise RuntimeError(f"records-api invocation error: {response['Payload'].read()!r}")
    payload = json.loads(response["Payload"].read())
    status = payload.get("statusCode", 500)
    body = json.loads(payload.get("body") or "{}")
    if status >= 400:
        raise RuntimeError(f"records-api returned {status}: {body}")
    return body


# ---------------------------------------------------------------------------
# Bedrock (Claude Haiku, raw InvokeModel -- no anthropic SDK dependency)
# ---------------------------------------------------------------------------

def _call_bedrock(system_prompt, messages):
    request_body = {
        "anthropic_version": "bedrock-2023-05-31",
        "max_tokens": 1024,
        "system": system_prompt,
        "tools": [UPDATE_TOOL],
        "messages": messages,
    }
    response = bedrock.invoke_model(
        modelId=BEDROCK_MODEL_ID,
        body=json.dumps(request_body),
        contentType="application/json",
        accept="application/json",
    )
    return json.loads(response["body"].read())


def _text_from(content_blocks):
    return "".join(b.get("text", "") for b in content_blocks if b.get("type") == "text")


def _handle_sms(body_text, today):
    system_prompt = (
        "You track the user's personal daily data (hours worked, weight, "
        "calories, notes, or any other attribute) via SMS. "
        f"Today's date is {today} (already resolved in the user's local "
        "timezone -- use it directly for phrases like 'today', 'yesterday', "
        "or a specific weekday; do not attempt to compute dates yourself). "
        "When the message describes something to record, call "
        "update_day_record with the correct date and attributes, then give a "
        "short, friendly one-sentence confirmation summarizing what was "
        "recorded for that date. If nothing needs recording, reply "
        "conversationally without calling the tool."
    )

    messages = [{"role": "user", "content": [{"type": "text", "text": body_text}]}]

    response = _call_bedrock(system_prompt, messages)
    messages.append({"role": "assistant", "content": response["content"]})

    # Bounded tool loop -- this task needs at most one round trip.
    if response.get("stop_reason") == "tool_use":
        tool_use = next(b for b in response["content"] if b.get("type") == "tool_use")
        try:
            result = _invoke_records_api(
                "PATCH",
                f"/records/{tool_use['input']['date']}",
                tool_use["input"]["attributes"],
            )
            tool_result_content = json.dumps(result)
            is_error = False
        except Exception as exc:  # noqa: BLE001
            tool_result_content = f"Failed to update record: {exc}"
            is_error = True

        messages.append(
            {
                "role": "user",
                "content": [
                    {
                        "type": "tool_result",
                        "tool_use_id": tool_use["id"],
                        "content": tool_result_content,
                        "is_error": is_error,
                    }
                ],
            }
        )
        response = _call_bedrock(system_prompt, messages)

    return _text_from(response["content"]) or "Got it."


# ---------------------------------------------------------------------------
# Entrypoint
# ---------------------------------------------------------------------------

def lambda_handler(event, context):
    try:
        params = _parse_form_body(event)
        signature = _get_header(event, "X-Twilio-Signature")
        url = _request_url(event)
        _validate_twilio_signature(url, params, signature)
    except TwilioAuthError:
        return {"statusCode": 403, "headers": {"Content-Type": "text/plain"}, "body": "Invalid signature"}
    except Exception as e:  # noqa: BLE001
        print(f"Unhandled error during request validation: {e!r}")
        return {"statusCode": 403, "headers": {"Content-Type": "text/plain"}, "body": "Bad request"}

    body_text = (params.get("Body") or "").strip()
    if not body_text:
        return _twiml_response(200, "Text me something like 'worked 8 hours today' and I'll log it.")

    try:
        today = datetime.now(ZoneInfo(TIMEZONE)).date().isoformat()
        reply = _handle_sms(body_text, today)
    except Exception as e:  # noqa: BLE001 - top-level safety net, mirrors handler.py
        print(f"Unhandled error: {e!r}")
        reply = "Sorry, something went wrong logging that -- please try again."

    return _twiml_response(200, reply)
