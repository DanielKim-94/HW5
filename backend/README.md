> Current setup, clean-run instructions and submission scope: [root README](../README.md). Earlier verification counts below describe development stages; they are not current completion evidence.

# Campus Customs agent team

Five PydanticAI agents share the same FastMCP server:
Boss coordinates; Inventory checks stock/supply; Accounting checks cash and
payments; Facilities handles rent; Customer Service writes unsent drafts.
Each role has its own instructions in `prompts/`; typed contracts and limits
are in `models.py`. Production model calls use exactly `gpt-6-luna` at
`https://api.portkey.ai/v1`, with `PORTKEY_API_KEY` loaded from the project root `.env` (parent workspace fallback). No alternate model or provider fallback is permitted.

Chat Completions uses `reasoning_effort: none`, verified with actual function
calling and PydanticAI structured output. All five agents share this configuration.
Outbound model/settings and returned model/request IDs plus safe Portkey routing
headers are recorded per ticket/agent/run in the audit. Missing or mismatched
model metadata stops before tool execution. The dated snapshot
`gpt-6-luna-2026-09-22` was verified; older 5.6 responses are historical failures,
not evidence of the current required model. See output/model_routing_checks.json
and output/agent_model_verification.json. No gateway settings were changed.

From HW5, install requirements (already installed in this environment):

```powershell
.\.venv\Scripts\python.exe -m pip install -r .\backend\requirements.txt
```

The working DB's operational schema was initialized through MCP in Problem 5.
To initialize a fresh working copy, run:

```powershell
.\.venv\Scripts\python.exe -m backend.cli initialize
```

To run one requested ticket later (this can create pending requests/drafts and
fulfill from existing stock, but cannot grant human approval):

```powershell
.\.venv\Scripts\python.exe -m backend.cli run 101 "Investigate the tee request and return blockers."
```

Use `--agent "Inventory"`, `--agent "Accounting"`, `--agent "Facilities"`,
or `--agent "Customer Service"` to start that role; Boss is the default.
Any starting role can ask any other relevant role for help. Delegates share
the ticket, budgets, and MCP connection, with separate message histories.

## Human payment decisions

Agents return the real pending approval ID. Review its exact amount, account,
obligation, and due date through MCP before deciding. A trusted local HUMAN
operator, never a model tool, can run:

```powershell
.\.venv\Scripts\python.exe -m backend.cli decide 101 <approval-id> --human-name "Your Name" --approve
.\.venv\Scripts\python.exe -m backend.cli decide 101 <approval-id> --human-name "Your Name" --deny
```

`--approve` records the human decision then executes the payment with fresh
cash/obligation checks. `--deny` can also revoke an approved, unexecuted request.
If the amount/due date changed, deny the stale request and request a new one.
If execution fails after approval, the approved request remains durable and
can be retried through `execute_approved_payment` when the issue is corrected.
Approvals do not authorize a different amount/account/reference.

The backend creates a random capability only for its MCP subprocess. It is
never placed in prompts, model tool arguments, source configuration, or audit
entries. Human decision/initialization tools are absent from agent tools.
Without that capability a directly connected coding assistant cannot grant
approval. This trusts the local OS operator; it is not a remotely authenticated
multi-user service. Future routes must authenticate humans and authorize
decisions server-side; never expose this method as an ordinary model tool.

## Audit and limits

Every actual graph node start/completion/failure, delegation, operational tool
attempt/result, approval request, human decision, and payment execution is
appended to `output/audit_trail.json`. Existing entries are preserved using a
file lock and atomic JSON replacement; malformed files cause an error.
Model responses and structured tool evidence are recorded, not private
reasoning. SQLite transactions and filesystem audit writes are separate;
after a crash reconcile using durable approval/payment records.

Defaults: 20 model requests, 30 successful function-tool calls plus at most
30 MCP attempts, 40,000 provider-reported tokens, 1,500 output tokens per
request, 60 graph nodes, 8 delegations, depth 3, and 180 seconds per ticket.
SDK retries are off; one schema/tool correction retry is allowed. Token checks
use reported usage and the final response may cross the total-token threshold.
Any-to-any delegation is subject to role/ticket topic checks and no ancestor
cycles. Top-level runs in one team are serialized; SQLite protects payment
transactions across processes. The model can still phrase an unrelated task:
topic checks are structural, and prompts/audit provide the semantic controls.

## Verification

```powershell
.\.venv\Scripts\python.exe -m unittest backend.test_safeguards -q
```

Offline tests use disposable copies and a FunctionModel simulator. They make
no live AI calls or real shop payments. Production Portkey/model metadata was verified in the preserved output evidence. A failed account/model route must be fixed without silently changing the required model. Historical setup verification: no ticket plan/resolution run was made
in Problem 5. Backend routes and dashboard are later problems.

References: [PydanticAI delegation](https://pydantic.dev/docs/ai/guides/multi-agent-applications/),
[compatible API providers](https://pydantic.dev/docs/ai/models/compatible-apis/),
[Portkey SDK gateway examples](https://github.com/Portkey-AI/portkey-python-sdk).


## Problem 7 dashboard API

From `backend/`, start the development API with the existing venv:

```powershell
..\.venv\Scripts\Activate.ps1
uvicorn main:app --reload --port 8000
```

Or use `..\.venv\Scripts\python.exe -m uvicorn main:app --reload --port 8000`.
It is currently running at http://127.0.0.1:8000/docs. Its recorded process tree
root is in `../output/backend_process.json`; stop the whole tree with
`taskkill /PID <recorded-pid> /T /F` after verifying the PID still belongs to this
backend. Reload cancels active runs and closes the MCP subprocess.

Read routes: GET `/tickets`, `/tickets/{ticket_id}`, `/cash`, `/approvals`,
`/activity`, `/runs/{run_id}`, `/health`. Activity is actual audit evidence,
with ticket/run filters and a sequence cursor. POST `/tickets/{ticket_id}/run`
returns 202 and a run ID; poll its status while reading activity.

All POST routes require `Authorization: Bearer <human-token>`. The local token
is stored in ignored `backend/.human_api_token`, or configured with
CAMPUS_HUMAN_API_TOKEN. Open that file locally and use the value in Swagger's
Authorize dialog. Never place it in an agent prompt, source control, or a model
tool argument. No token is returned by the API. This is local bearer access,
not a production multi-user identity system.

Prepare payment: POST `/tickets/101/payments/prepare` with
`{"kind":"invoice","ref_id":501}` (rent uses ticket 102/kind rent/ref_id 1).
Prepare purchase: POST `/tickets/103/purchases/prepare` with vendor_id, qty,
supplier_evidence, and optional account. Vendor/product evidence is required
and must be reviewed; recorded unit_cost is a procurement assumption, not a
verified supplier quote. Preparation never spends cash.

Review GET `/approvals`, then POST `/approvals/{approval_id}/approve` with:

```json
{"ticket_id":101,"request_type":"payment","human_name":"Your Name","approve":true}
```

Use request_type purchase and the appropriate ticket for a purchase. The HTTP
route combines approval and spending in ONE MCP transaction; insufficient cash,
stale facts, or vendor shipping blocks leave the request pending without any
debit. A replay returns the same payment. Purchases record an order and cash-out,
not received stock. POST `/approvals/{approval_id}/deny` accepts the same identity
and request fields without approve, to deny/revoke an unexecuted request.

POST `/reset` requires `{"confirmation":"RESET_WORKING_DATABASE"}` plus the human
token. It restores the original DB into the working copy via MCP, recreates
empty extensions, clears approval IDs, and preserves the historical audit.
Mutation requests return 409 while an agent run is active. Job status is held
in memory; reload loses it, while the audit and approval records remain durable.
No interrupted model job is automatically resumed.

Seven operational extension tables now exist: the original five plus
purchase_approvals and purchases. Payments.kind purchase references purchases.id.
The earlier five-table count is the Problem 5 snapshot. The CLI decision command
still supports the original payment-only flow; dashboard purchase and atomic
approval handling are available through the HTTP routes.

Run all current offline integration checks:

```powershell
.\.venv\Scripts\python.exe -m unittest backend.test_api backend.test_safeguards -q
```

Run that test command from HW5, because backend is the Python package. Fifteen tests passed.
Live read-only HTTP checks are recorded in `../output/backend_smoke.json`.
No production model run, shop payment/purchase, or reset was invoked during build.
Full routes, schema fields, security boundaries, and limits: `../output/harness.md`.
