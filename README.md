# Campus Customs — HW5

Five PydanticAI agents (Boss, Inventory, Accounting, Facilities, Customer Service)
use a shared FastMCP server, a FastAPI backend, and a React/Vite/TypeScript dashboard.
All production agent calls require **gpt-6-luna through Portkey**. The response
model must match; the app refuses a silent model fallback.

## Submitted results and evidence

The submitted working database records all three tickets resolved and checking
at **160**: **3,400 − 840 − 2,400 = 160**. These are different completion scopes:

- **101:** user-approved classroom simulation of receipt and fulfillment of one
  size-S tee on September 5, 2026. The paid invoice is assumed to cover one tee;
  five calendar days start with the recorded August 31 payment. No physical
  delivery is claimed and simulation added no payment.
- **102:** human-approved rent payment of 2,400; lease next due October 2.
- **103:** pricing request closed at 58 per hoodie with an **unsent conditional
  quote**. Only 8 of 20 requested are in stock; all 20 are not guaranteed.
  No customer acceptance, hoodie fulfillment, or revenue is recorded.

**The completion criteria for 101 and 103 are user-approved, not
instructor-confirmed.** Earlier failed, blocked and completed-but-open attempts
are historical. Later resets cleared committed completion; scoped recovery
restored corroborated authorized records without replaying payments or simulation.
See [investigation](output/discrepancy_investigation.md),
[current manifest](output/recovered_completion_manifest.json), and
[cash evidence](output/payment_reconciliation.json).

Open `output/desk_tickets.html` directly for Expected, Actual, Cash and Reflection.
It is a static report; the live dashboard is a separate app.

## Layout

```text
AI_prompts.md                 Prompts for all 11 problems
README.md / requirements.txt  Setup and Python dependencies
.env.example / .gitignore     Local configuration template and exclusions
.mcp.json                     Portable project MCP connection
data/campus_customs.db        Unchanged supplied original
data/campus_customs_new.db    Submitted working results
mcp_server/server.py          FastMCP entry point
mcp_server/operations.py      Guarded operational workflows
mcp_server/READme.md           Tool documentation
backend/main.py               FastAPI routes
backend/models.py             Shared types and limits
backend/prompts/*.md          Five role prompts
frontend/                     React, Vite, TypeScript; npm lockfile
output/harness.md             Tables, agents, tools, safeguards and routes
output/mcp_smoke.json          Recorded actual MCP smoke calls
output/audit_trail.json        Preserved append-only run history
output/desk_tickets.html       Expected/Actual/Cash/Reflection report
output/design.md              Dashboard design
output/screenshots/           Actual dashboard captures and metadata
output/resolved_tickets.md    Current completion explanation
output/github_url.txt         Public repository URL, added when published
```

## Setup from a fresh clone (Windows PowerShell)

Use Python 3.14 (the version used for this project) and Node.js 22 or newer.
From the repository root:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
Copy-Item .env.example .env
# Edit .env locally and set PORTKEY_API_KEY. Never commit the real file.
```

Environment variables take precedence. The project-root `.env` is loaded next;
the parent workspace `.env` remains a compatibility fallback for the original setup.
No API key is supplied with this repository.

## Start MCP, backend and frontend

The portable `.mcp.json` assumes the coding assistant starts in the project root
with this virtual environment's Python on PATH. Activate it before launching the
assistant, or configure the assistant with absolute paths to
`.venv/Scripts/python.exe` and `mcp_server/server.py`. MCP clients differ in local
configuration support; this config uses the standard `mcpServers` STDIO shape.
Do not give an agent the human capability or API bearer token.

To start the STDIO server manually from the project root:

```powershell
.\.venv\Scripts\python.exe mcp_server/server.py
```

It waits for an MCP client, not browser HTTP requests. The backend starts its own
MCP subprocess, so a separate manual server is not needed for the dashboard.
The server resolves the database relative to its source file.

In terminal 1:

```powershell
cd backend
..\.venv\Scripts\python.exe -m uvicorn main:app --host localhost --port 8000
```

Keep reload off during recorded runs so edits do not interrupt the team. In terminal 2:

```powershell
cd frontend
npm.cmd ci
npm.cmd run dev
```

Open **http://localhost:5174**. The frontend connects to
**http://localhost:8000**, whose CORS allows the configured Vite origin.
API docs: http://localhost:8000/docs. GET /health reports the actual MCP database
path and PID. Unlock human actions using the locally generated
`backend/.human_api_token`; it is a local operator credential, not a production
multi-user identity system. Do not share or commit it.

## Reset and perform a clean three-ticket run

The shipped working database contains completed evidence. **Reset is optional
and destructive to its current records**, not a prerequisite for viewing results.
Preserve a SQLite backup and the audit before choosing a fresh run. Never edit
or replace the original database. The dashboard's **Reset working database**
button invokes the authenticated backend POST /reset with confirmation
`RESET_WORKING_DATABASE`. It restores the original through MCP, initializes
extension tables, and preserves the audit. Current approvals, quotes, simulated
fulfillment and completion records are cleared; prior screenshots become
historical. Baseline is three open tickets and checking 3,400. Do not reset
between tickets. Record a distinct run label and audit/reset sequence.

1. Confirm GET /health's database path, three open ticket rows and checking 3,400.
   Unlock human actions. Run **one ticket at a time**, starting with 101.
2. For 101, investigate stock and linked invoice. Review the prepared invoice
   501 request and approve 840 only once if you choose to pay it. Confirm checking
   2,560 and the invoice paid. Payment alone does not resolve the order. Continue
   investigation if needed. To reproduce the submitted classroom criterion,
   prepare the simulated-restock proposal and explicitly acknowledge its
   assumptions. Plan approval is separate from receipt. Review the effect of
   advancing the shared shop date before advancing it to September 5, then
   separately confirm **simulated receipt and fulfillment**. Do not claim actual
   delivery. Capture only after backend and dashboard confirm resolution.
3. For 102, verify lease 1, rent 2,400 and current cash. Prepare a request if none
   is pending, then review and approve once. Confirm payment, lease next due
   October 2, ticket resolved and checking 160. The submitted monthly recurrence
   is an implementation convention. Capture the confirmed result.
4. For 103, check 8 medium hoodies against 20 requested and recorded price 58.
   Keep 58 and prepare a pricing-decision proposal stating that the quote is
   conditional and unsent, with all 20 not guaranteed. A human must acknowledge
   and apply pricing-only closure. This is not fulfillment or customer acceptance.
   No payment or revenue is involved; checking remains 160. Capture resolution.
5. Check the current database, API, approval ledger and audit. A job reporting
   Completed or Blocked is not resolution. Preserve failed attempts, and keep
   new screenshots and run evidence separate from the submitted captures.

These steps reproduce **user-approved classroom criteria**, not guaranteed model
behavior or an instructor-approved physical shop workflow. If a required model
is unavailable or a tool/run fails, inspect the evidence and stop rather than
changing models, inventing facts, or forcing a status. Humans approve payments;
cash cannot become negative, no revenue is modeled, and all messages remain drafts.

## Verification

```powershell
.\.venv\Scripts\python.exe -m unittest backend.test_api backend.test_safeguards backend.test_model -q
cd frontend
npm.cmd run build
npm.cmd test
```

Backend tests use disposable databases and simulated models, not live payments.
Browser tests may use fixtures; they verify UI behavior, not real ticket completion.
Actual capture script: `node scripts/capture-ticket.mjs 101
output/recovered_completion_manifest.json --visible` (run from frontend; repeat
for the selected ticket). It requires real API/UI resolution; choose a new
manifest for a new run to avoid overwriting submitted evidence.

## Security and submission

Git excludes real `.env` files, generated human tokens, virtual environments,
node_modules, build outputs, logs, and local diagnostic backups. Canonical audit,
both required databases and current screenshot evidence are included. The public
project contains assignment scenario names and historical audit metadata.
The submission review checks staged files for known local secret values without
printing them. Local diagnostic copies remain on disk but are not public artifacts.
Submit the repository URL from `output/github_url.txt` to Canvas yourself.
