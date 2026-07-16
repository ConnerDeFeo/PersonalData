"""
Single Lambda entrypoint for the personal-data-tracking REST API.

Routes (logical contract implemented here; API Gateway forwards everything
via a single ANY /{proxy+} catch-all):

    GET    /records                 list records (optional ?start=&end=)
    GET    /records/{date}          get one record
    POST   /records                 create/upsert a record
    PUT    /records/{date}          full replace of a record's attributes
    PATCH  /records/{date}          merge attributes into a record
    DELETE /records/{date}          delete an entire record
    DELETE /records/{date}/{attr}   remove a single attribute from a record

All dates are strings in YYYY-MM-DD format and are the DynamoDB partition
key. "date" is a DynamoDB *reserved word* -- any raw expression string
(FilterExpression, UpdateExpression, ConditionExpression) that references the
attribute name must use an ExpressionAttributeNames alias. Key-only operations
(get_item/put_item/delete_item with Key={"date": ...}) don't need one since
they aren't expressions, and boto3's Attr()/Key() condition helpers (used in
list_records below) generate the alias for you automatically.
"""

import json
import os
import re
from decimal import Decimal

import boto3
from boto3.dynamodb.conditions import Attr

DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

ALLOWED_ATTRS = ("hours_worked", "hours_worked_out", "hours_reading", "weight", "calories")

dynamodb = boto3.resource("dynamodb")
table = dynamodb.Table(os.environ["TABLE_NAME"])

CORS_HEADERS = {
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Headers": "Content-Type,X-Api-Key,Authorization",
    "Access-Control-Allow-Methods": "GET,POST,PUT,PATCH,DELETE,OPTIONS",
}


class ApiError(Exception):
    """Raised for expected, user-facing errors (bad input, not found, etc.)."""

    def __init__(self, status, message):
        super().__init__(message)
        self.status = status
        self.message = message


# ---------------------------------------------------------------------------
# Decimal <-> JSON helpers
# ---------------------------------------------------------------------------

def _to_dynamo(value):
    """Recursively convert JSON-decoded values into DynamoDB-safe values.

    DynamoDB's Number type is represented by boto3 as Decimal; floats are
    rejected outright by the SDK, so every float/int in the payload must be
    converted to Decimal (via its string repr, to avoid binary float error).
    """
    if isinstance(value, bool):
        return value
    if isinstance(value, float):
        return Decimal(str(value))
    if isinstance(value, int):
        return Decimal(value)
    if isinstance(value, dict):
        return {k: _to_dynamo(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_to_dynamo(v) for v in value]
    return value


def _from_dynamo(value):
    """Recursively convert DynamoDB values (Decimal) back into JSON-safe values."""
    if isinstance(value, Decimal):
        # Whole numbers -> int, otherwise float, so JSON output looks natural.
        if value % 1 == 0:
            return int(value)
        return float(value)
    if isinstance(value, dict):
        return {k: _from_dynamo(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_from_dynamo(v) for v in value]
    return value


# ---------------------------------------------------------------------------
# Response / parsing helpers
# ---------------------------------------------------------------------------

def _response(status, body=None):
    payload = {} if body is None else body
    return {
        "statusCode": status,
        "headers": {**CORS_HEADERS, "Content-Type": "application/json"},
        "body": json.dumps(payload),
    }


def _parse_body(event):
    raw = event.get("body")
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
    except (TypeError, ValueError):
        raise ApiError(400, "Request body must be valid JSON")
    if not isinstance(parsed, dict):
        raise ApiError(400, "Request body must be a JSON object")
    return parsed


def _validate_date(date_value):
    if not date_value or not isinstance(date_value, str) or not DATE_RE.match(date_value):
        raise ApiError(400, "date must be a string in YYYY-MM-DD format")
    return date_value


def _validate_attrs(body):
    attrs = {k: v for k, v in body.items() if k != "date"}
    for k, v in attrs.items():
        if k not in ALLOWED_ATTRS:
            raise ApiError(400, f"Unknown attribute '{k}'. Allowed: {', '.join(ALLOWED_ATTRS)}")
        if isinstance(v, bool) or not isinstance(v, (int, float)):
            raise ApiError(400, f"Attribute '{k}' must be a number")
    return attrs


# ---------------------------------------------------------------------------
# Route handlers
# ---------------------------------------------------------------------------

def list_records(query_params):
    query_params = query_params or {}
    start = query_params.get("start")
    end = query_params.get("end")

    if start:
        _validate_date(start)
    if end:
        _validate_date(end)

    scan_kwargs = {}
    if start and end:
        scan_kwargs["FilterExpression"] = Attr("date").between(start, end)
    elif start:
        scan_kwargs["FilterExpression"] = Attr("date").gte(start)
    elif end:
        scan_kwargs["FilterExpression"] = Attr("date").lte(end)

    items = []
    kwargs = dict(scan_kwargs)
    while True:
        result = table.scan(**kwargs)
        items.extend(result.get("Items", []))
        last_key = result.get("LastEvaluatedKey")
        if not last_key:
            break
        kwargs = dict(scan_kwargs)
        kwargs["ExclusiveStartKey"] = last_key

    items.sort(key=lambda item: item["date"])
    return _response(200, {"records": [_from_dynamo(item) for item in items]})


def get_record(date):
    _validate_date(date)
    result = table.get_item(Key={"date": date})
    item = result.get("Item")
    if not item:
        raise ApiError(404, f"No record found for date {date}")
    return _response(200, _from_dynamo(item))


def create_record(body):
    date = body.get("date")
    _validate_date(date)
    _validate_attrs(body)
    item = _to_dynamo(body)
    item["date"] = date
    table.put_item(Item=item)
    return _response(201, _from_dynamo(item))


def replace_record(date, body):
    _validate_date(date)
    if "date" in body and body["date"] != date:
        raise ApiError(400, "date in body must match date in path")
    _validate_attrs(body)
    item = _to_dynamo(body)
    item["date"] = date
    table.put_item(Item=item)
    return _response(200, _from_dynamo(item))


def patch_record(date, body):
    # Note: update_item is an upsert -- PATCH on a date with no existing
    # record creates one with just the given attributes, rather than 404ing.
    # For a personal tracker this is treated as a convenience, not a bug.
    _validate_date(date)
    attrs = _validate_attrs(body)
    if not attrs:
        raise ApiError(400, "No attributes provided to update")

    update_parts = []
    expr_names = {}
    expr_values = {}
    for i, (key, value) in enumerate(attrs.items()):
        name_placeholder = f"#a{i}"
        value_placeholder = f":v{i}"
        expr_names[name_placeholder] = key
        expr_values[value_placeholder] = _to_dynamo(value)
        update_parts.append(f"{name_placeholder} = {value_placeholder}")

    update_expression = "SET " + ", ".join(update_parts)

    result = table.update_item(
        Key={"date": date},
        UpdateExpression=update_expression,
        ExpressionAttributeNames=expr_names,
        ExpressionAttributeValues=expr_values,
        ReturnValues="ALL_NEW",
    )
    return _response(200, _from_dynamo(result["Attributes"]))


def delete_record(date):
    _validate_date(date)
    result = table.delete_item(Key={"date": date}, ReturnValues="ALL_OLD")
    if "Attributes" not in result:
        raise ApiError(404, f"No record found for date {date}")
    return _response(200, {"deleted": date})


def delete_attribute(date, attr):
    _validate_date(date)
    if attr == "date":
        raise ApiError(400, "Cannot remove the date attribute")
    if attr not in ALLOWED_ATTRS:
        raise ApiError(400, f"Unknown attribute '{attr}'. Allowed: {', '.join(ALLOWED_ATTRS)}")

    existing = table.get_item(Key={"date": date}).get("Item")
    if not existing:
        raise ApiError(404, f"No record found for date {date}")
    if attr not in existing:
        raise ApiError(404, f"Attribute '{attr}' not present on {date}")

    result = table.update_item(
        Key={"date": date},
        UpdateExpression="REMOVE #a",
        ExpressionAttributeNames={"#a": attr},
        ReturnValues="ALL_NEW",
    )
    return _response(200, _from_dynamo(result["Attributes"]))


# ---------------------------------------------------------------------------
# Router
# ---------------------------------------------------------------------------

def _route(method, segments, query_params, body):
    # segments is the path split on "/", with the leading "records" already
    # required and empty strings stripped, e.g. ["records"], ["records", "2026-07-16"]
    if not segments or segments[0] != "records":
        raise ApiError(404, "Not found")

    rest = segments[1:]

    if len(rest) == 0:
        if method == "GET":
            return list_records(query_params)
        if method == "POST":
            return create_record(body)
        raise ApiError(405, f"Method {method} not allowed on /records")

    if len(rest) == 1:
        date = rest[0]
        if method == "GET":
            return get_record(date)
        if method == "PUT":
            return replace_record(date, body)
        if method == "PATCH":
            return patch_record(date, body)
        if method == "DELETE":
            return delete_record(date)
        raise ApiError(405, f"Method {method} not allowed on /records/{{date}}")

    if len(rest) == 2:
        date, attr = rest
        if method == "DELETE":
            return delete_attribute(date, attr)
        raise ApiError(405, f"Method {method} not allowed on /records/{{date}}/{{attr}}")

    raise ApiError(404, "Not found")


def lambda_handler(event, context):
    method = event.get("httpMethod", "")

    if method == "OPTIONS":
        return _response(200, {})

    path = event.get("path") or ""
    segments = [s for s in path.split("/") if s]
    query_params = event.get("queryStringParameters") or {}

    try:
        body = _parse_body(event) if method in ("POST", "PUT", "PATCH") else {}
        return _route(method, segments, query_params, body)
    except ApiError as e:
        return _response(e.status, {"error": e.message})
    except Exception as e:  # noqa: BLE001 - top-level safety net for a Lambda handler
        print(f"Unhandled error: {e!r}")
        return _response(500, {"error": "Internal server error"})
