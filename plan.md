# Plan: Dashboard frontend + strict-column backend

## Context

`PersonalData` is an AWS-serverless personal tracker: a schemaless DynamoDB table
(`personal-data`, one item per `date`), a records-CRUD Lambda (`src/handler.py`)
behind an API-key-protected API Gateway proxy, and a Twilio SMS webhook
(`src/twilio_handler.py`) that uses Claude Haiku (Bedrock) to turn texts into
`PATCH /records/{date}` writes. There is **no frontend** yet, and the schema is
**fully dynamic** — the LLM or any caller can write arbitrary attribute names.

This change adds the final piece:
1. A **read-only React dashboard** (Vite + TS + Tailwind) that visualizes the data.
2. **Strict columns** — only `hours_worked`, `hours_worked_out`, `hours_reading`,
   `weight`, `calories` (all numbers) may be written, by anyone (HTTP or SMS).
3. **Auth split** — GET endpoints become public so the SPA needs no secret; writes
   stay behind the API key; Twilio stays signature-protected.

Decisions confirmed with the user: dashboard is read-only; hosted locally
(`npm run dev`) only; the center donut splits the three *hours* fields;
averages count only days where the field was present (missing ≠ 0).

The project standardizes on **snake_case** field names (matching the user's
stated columns). Today's Twilio tool/prompt use camelCase (`hoursWorked`) — this
must change in lockstep or every SMS will 400 against the new validation.

---

## Part A — Backend: strict columns (`src/handler.py`)

Single choke point. Twilio writes by directly invoking this same Lambda, so
validating here covers **both** the HTTP API and the SMS path — do not duplicate
the rule into `twilio_handler.py`.

1. Add a module constant + validator near the other helpers:
   ```python
   ALLOWED_ATTRS = ("hours_worked", "hours_worked_out", "hours_reading", "weight", "calories")

   def _validate_attrs(body):
       attrs = {k: v for k, v in body.items() if k != "date"}
       for k, v in attrs.items():
           if k not in ALLOWED_ATTRS:
               raise ApiError(400, f"Unknown attribute '{k}'. Allowed: {', '.join(ALLOWED_ATTRS)}")
           if isinstance(v, bool) or not isinstance(v, (int, float)):
               raise ApiError(400, f"Attribute '{k}' must be a number")
       return attrs
   ```
2. Call `_validate_attrs(body)` at the top of `create_record` (`handler.py:169`),
   `replace_record` (`handler.py:178`), and `patch_record` (`handler.py:188`) —
   reuse its returned `attrs` in `patch_record` instead of the current inline
   comprehension at `handler.py:193`.
3. `delete_attribute` (`handler.py:227`): reject `attr not in ALLOWED_ATTRS` with 400
   (alongside the existing `date` guard).

## Part B — Backend: constrain the LLM tool (`src/twilio_handler.py`)

The belt to Part A's suspenders — keeps the model from emitting bad fields at all.
4. `UPDATE_TOOL.input_schema` (`twilio_handler.py:53`): replace the open
   `attributes` object with enumerated numeric properties and
   `"additionalProperties": false`:
   ```python
   "attributes": {
       "type": "object",
       "additionalProperties": False,
       "properties": {
           "hours_worked":     {"type": "number"},
           "hours_worked_out": {"type": "number"},
           "hours_reading":    {"type": "number"},
           "weight":           {"type": "number"},
           "calories":         {"type": "number"},
       },
   }
   ```
5. **snake_case-ify the prompt (couples with Part A — ship together):**
   - The tool `description` example must read `{"hours_worked": 8}`, not `hoursWorked`.
   - The system prompt (`_handle_sms`, `twilio_handler.py:194`) must name the exact
     five snake_case fields as the only recordable data.
   Without this the model emits camelCase → new validation 400s → every SMS fails.

Data note: any pre-existing camelCase items would fail validation/render. Repo is
fresh scaffolding, so we **accept the reset** (no migration) — call this out.

## Part C — Backend: auth split (`terraform/apigateway.tf`)

Make GET public; keep writes keyed; Twilio unchanged. Writes staying behind the
key is a security boundary — keep it.

6. Replace the single `ANY /{proxy+}` method+integration (`apigateway.tf:16-35`)
   with per-method methods via `for_each` over a map (DRY):
   ```hcl
   locals {
     proxy_methods = {
       GET    = false   # public
       POST   = true
       PUT    = true
       PATCH  = true
       DELETE = true
     }
   }
   ```
   One `aws_api_gateway_method` + one `aws_api_gateway_integration` per entry,
   `api_key_required = each.value`, on `aws_api_gateway_resource.proxy`. Do the
   same for the root resource (or just drop root to `GET` public — it's not part
   of the contract).
7. **Update the deployment `redeployment` trigger** (`apigateway.tf:87-98`): it
   currently hashes `proxy_any`/`root_any` IDs that will no longer exist. Point it
   at the new `for_each` method/integration IDs (e.g. `values(...).*.id`), or the
   stage won't redeploy and the auth split silently won't take effect.
8. CORS needs **no new work**: the Lambda already returns
   `Access-Control-Allow-Origin: *`, and a bare GET with no custom headers is a
   CORS "simple request" (no preflight). Constraint: the frontend must send **no
   custom headers** on GETs. Leave the API-key/usage-plan resources as-is (still
   used by writes).

## Part D — Frontend (`frontend/`, greenfield, read-only)

Stack: Vite + React + TS + Tailwind. **One** charting dep: `recharts` (covers
donut + line charts). API base URL from `VITE_API_BASE` (`.env`). Fetch **all**
records once via `GET /records`, derive everything client-side. Follow the
`dataviz` skill for palette/legibility (light + dark). Keep every file < 150 lines.

Files:
- `frontend/src/api.ts` — `Record` type (`{date; hours_worked?; hours_worked_out?;
  hours_reading?; weight?; calories?}`), `fetchRecords()` (plain GET, no headers).
- `frontend/src/stats.ts` — **pure** derivations (the only place real bugs hide):
  - `currentWeek(records)` → 7 dates Sun→Sat for the week containing today,
    each joined to its record (or empty).
  - `weekdayAverages(records)` → for each weekday 0(Sun)–6(Sat), the average of
    each field over all records on that weekday, **counting only present values**.
  - `hoursDonut(records)` → all-time average (present-only) of the 3 hours fields.
  - `trend(records, field)` → date-sorted `{date, value}` series, skipping days
    missing that field.
- `frontend/src/components/WeekRow.tsx` — top row: current week Sun→Sat table,
  columns = the 5 fields.
- `frontend/src/components/HoursDonut.tsx` — center donut (Recharts `PieChart`),
  3 hours fields.
- `frontend/src/components/TrendCharts.tsx` — right: three Recharts `LineChart`s —
  `hours_worked` over time, `weight` over time, `calories` over time.
  ("Total hours worked over time" read plainly as the `hours_worked` column, not a
  sum of the three — that would duplicate the donut. Flagged for correction if wrong.)
- `frontend/src/components/WeekdayAverages.tsx` — bottom row: Sun→Sat, each cell
  the all-time average of that field on that weekday.
- `frontend/src/components/DayDetail.tsx` — native `<input type="date">`; shows the
  selected day's record (from the already-fetched list; no extra call).
- `frontend/src/App.tsx` — layout: top WeekRow; middle HoursDonut + TrendCharts;
  bottom WeekdayAverages; DayDetail picker. Single `useEffect` fetch → memoized
  derivations passed down.
- Standard Vite/Tailwind scaffold (`package.json`, `vite.config.ts`,
  `tailwind.config.js`, `index.css`, `main.tsx`, `.env.example`).

## Critical files
- `src/handler.py` — allow-list + validation (Part A)
- `src/twilio_handler.py` — tool schema + prompt snake_case (Part B)
- `terraform/apigateway.tf` — per-method auth + deployment trigger (Part C)
- `frontend/**` — new dashboard (Part D)
- `README.md` — document the fixed schema, the public-GET/keyed-write split, and
  frontend run steps.

---

## Verification (exercise the boundary, not just typecheck)

Backend (after `terraform apply`, using the `invoke_url`):
- `curl "$URL/records"` with **no** key → **200** (public read works).
- `curl -X POST "$URL/records" -H 'content-type: application/json' -d
  '{"date":"2026-07-16","mood":"good"}'` with the key → **400** (unknown attr).
- Same POST with `{"weight":"heavy"}` → **400** (non-number).
- `curl -X POST "$URL/records" -d '{...}'` with **no** key → **403** (writes locked).
- One valid `{"date":...,"hours_worked":8}` POST with key → **201**.
- SMS "worked 8 hours today" → record written with `hours_worked`, friendly reply
  (confirms snake_case prompt + validation agree).

Frontend:
- `cd frontend && npm i && npm run dev`; dashboard loads against `VITE_API_BASE`,
  all four regions render, date picker shows a chosen day.
- One assert-based self-check on `stats.ts` (`node`/vitest, no framework): feed a
  small fixture spanning known weekdays with some fields missing, assert
  `weekdayAverages` buckets by the right weekday and averages **over present values
  only** — the one spot a weekday-indexing / missing-skip bug would hide.
