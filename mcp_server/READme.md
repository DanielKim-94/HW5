> Current setup, clean-run instructions and submission scope: [root README](../README.md). Earlier verification counts below describe development stages; they are not current completion evidence.

# Campus Customs shared MCP server

Every HW5 agent uses this FastMCP server. `server.py` resolves
`../data/campus_customs_new.db` relative to itself, independent of launch
location. The original database is never opened by the server. Read tools
use read-only connections; operational changes use parameterized SQL with
foreign keys and transactions in `operations.py`. No arbitrary SQL tool exists.

## Agents and tools

Boss coordinates, Inventory checks stock/supply, Accounting handles cash-out
obligations and price arithmetic, Facilities handles rent, and Customer Service
writes unsent drafts. Their PydanticAI implementation is in `../backend/` with
one role prompt each. All production model calls use `gpt-6-luna` through
Portkey with `PORTKEY_API_KEY`; the MCP server itself makes no AI API calls.

| Tool | Ticket | Tables read / changed |
| --- | --- | --- |
| get_customer_order_context | 101 | Reads tickets, inventory, pricing, invoices, vendors, desk, cash_accounts |
| get_rent_payment_context | 102 | Reads tickets, leases, desk, cash_accounts, invoices, payments |
| get_bulk_pricing_context | 103 | Reads tickets, inventory, pricing |
| get_ticket_context | Any | Reads tickets, desk and extension records |
| get_vendor_shipping_status | 101/103 | Reads tickets, vendors, invoices, desk |
| request_payment_approval | 101/102 | Reads obligation, ticket, date and cash; writes payment_approvals |
| get_payment_approval | 101/102 | Reads payment_approvals |
| execute_approved_payment | 101/102 | Reads approved request/obligation/date/cash; updates payments, cash_accounts, payment_approvals, tickets and invoices or leases |
| save_message_draft | Any | Reads ticket/date; writes message_drafts |
| save_quote_draft | 103 | Reads ticket/pricing/date; writes quote_drafts |
| plan_vendor_shipment | 101/103 | Reads ticket/vendor/invoices/date; writes shipment_plans |
| fulfill_customer_order | 101 | Reads ticket/stock/date; updates inventory, fulfillments and tickets |
| initialize_shop_tools | Human setup only | Creates five extension tables and two guard triggers |
| record_human_payment_decision | Human only | Reads request/date; updates payment_approvals |

Fourteen tools are registered. Twelve shop tools are accessible to agents;
the two human-only tools require a trusted capability absent from prompts and
model tool schemas. The backend's constrained wrapper binds every agent call
to the current ticket. Original context tools return full actual database rows,
with nullable missing related rows and relevant uncertainty flags.

Extension tables: payment_approvals binds a human decision to a payment's exact
ticket/reference/amount/account/due date; message_drafts stores unsent text;
quote_drafts stores one unsent quote per ticket; fulfillments makes stock
changes replay-safe; shipment_plans stores supply drafts without adding stock.
Actual fields, foreign keys, and constraints are in `../output/harness.md`.

## Business safeguards

- Use desk.date_today, not computer time. Read vendor lead_days from the DB.
- Any open unpaid vendor invoice blocks shipment planning. Plans are drafts,
  never actual shipment or receipt. Calendar-day estimates are labeled unconfirmed.
- Every payment needs a stored HUMAN decision. Agents may request/read approval
  but cannot grant it. The trusted CLI supplies a random capability only to its
  own MCP subprocess. A normal coding-assistant connection has no such capability.
- Recheck exact obligation and funds under BEGIN IMMEDIATE; refuse insufficient
  cash. Atomically debit the account, insert payment, update invoice/lease and
  ticket, and mark approval executed. Replays never double-charge. Cash cannot
  become negative or increase. No revenue is modeled.
- New payment convention: kind invoice/ref_id invoice ID, or kind rent/ref_id
  lease ID. Rent recurrence advances one calendar month from old due date,
  clamping month end; this was unspecified in the original database.
- Messages and quotes remain drafts. Quotes cannot be below recorded cost
  (an added conservative safeguard), don't change global pricing, and don't
  credit cash. Stock fulfillment needs actual exact-size inventory.
- No confirmed-delivery/restock tool exists yet; never invent inventory.
  Supplier evidence text is not independently verified. Discount acceptance
  and bulk fulfillment policies remain unspecified.

## Setup, connection, and human decisions

Use the existing HW5 venv. From HW5:

```powershell
.\.venv\Scripts\python.exe -m pip install -r .\backend\requirements.txt
.\.venv\Scripts\python.exe -m backend.cli initialize
```

Initialization was completed through MCP in Problem 5. It is idempotent.
Workspace `.mcp.json` and `.codex/config.toml` save connection definitions;
Codex also has user-level campus-customs registration because the installed CLI
didn't load the project-local entry. Configure Python and server.py using their
absolute paths. STDIO is the entry-point transport. Restart the assistant MCP
connection to discover expanded tools.

For trusted human approval/denial and agent run commands, see
`../backend/README.md`. Do not give the human capability to a model. Local CLI
identity trusts the OS operator; future web routes require real authentication
and server-side authorization. No human payment was approved during setup.

## Audit, limits, and validation

The backend appends actual graph steps, delegations, MCP attempts/results,
approval requests and decisions to `../output/audit_trail.json`, preserving
previous entries with locking and atomic replacement. Corrupt logs fail closed.
DB and audit writes are separate: reconcile durable payment records after a
crash. Direct external MCP clients are not part of the backend agent loop;
they do not automatically generate its audit events.

Default shared tree limits: 20 model requests, 30 successful function-tool calls
and at most 30 MCP attempts, 40,000 reported tokens, 1,500 output tokens/request,
60 graph nodes, 8 delegations, depth 3, 180 seconds/ticket. Same-ticket relevant
any-to-any delegation is supported, excluding self/ancestor cycles. Structural
relevance checks cannot prove free-text task relevance. Token limits rely on
reported usage and the last response may cross the total threshold. SDK retries
are off; one corrective PydanticAI retry is allowed.

Nine offline integration tests passed on disposable copies:

```powershell
.\.venv\Scripts\python.exe -m unittest backend.test_safeguards -q
```

Read-only stdio discovery/contexts are saved in `../output/team_validation.json`.
All real tickets and original-table business records remain unchanged; the
working DB now has the five empty extension tables. No live model run, payment,
customer/vendor contact, or ticket resolution occurred. Original Problem 4
protocol outputs remain in mcp_smoke.json; native-assistant tests are still
pending a refreshed connection. `smoke_test.py` can repeat the original three
protocol calls, explicitly distinguishing them from native assistant calls.

References: [FastMCP quickstart](https://github.com/PrefectHQ/fastmcp/blob/main/docs/getting-started/quickstart.mdx),
[PydanticAI delegation](https://pydantic.dev/docs/ai/guides/multi-agent-applications/),
[compatible providers](https://pydantic.dev/docs/ai/models/compatible-apis/).


## Problem 7 backend additions

FastAPI `../backend/main.py` now serves the dashboard API on port 8000. Shop
reads and changes remain MCP-only. Nine new tools bring the current total to
23 (15 agent-accessible, 2 dashboard-wide reads, 6 human-only administrative).
The earlier fourteen-tool count is the Problem 5 snapshot.

| Added tool | Reads / changes |
| --- | --- |
| list_shop_tickets | Read the three tickets and desk date |
| get_checking_balance | Read checking and desk date |
| get_cash_obligations | Read cash, invoices, leases, payments and date for the current ticket |
| list_approval_requests | Read payment/purchase requests |
| request_purchase_approval | Read ticket, stock, vendor, pricing, cash/date; write pending purchase_approvals |
| approve_and_execute_payment | Human-only atomic decision and existing payment transaction |
| approve_and_execute_purchase | Human-only atomic verification, cash debit, purchase/payment insert, ticket note, request update; no stock receipt |
| deny_prepared_request | Human-only denial/revocation of unexecuted requests |
| reset_working_database | Human-only SQLite backup from read-only original into fixed working DB, followed by extension initialization |

purchase_approvals binds SKU/size/vendor/qty/cost/account/lead time to a pending
human request. purchases records an ordered item, not delivery. A partial unique
index permits only one pending/executed purchase per ticket. Preparation never
spends; execution refuses stale facts, insufficient funds, or any unpaid vendor
invoice. It uses recorded unit_cost as an explicit assumption and requires
supplier evidence for human review. No supplier contact or stock creation occurs.
Payments.kind purchase/ref_id purchases.id is the added reference convention.
Actual fields and table mappings are in the harness.

The HTTP bearer token and MCP human capability are distinct and never passed to
agents. All administrative tools remain excluded from the agent allowlist.
A request must be pending to approve; executed requests replay without another
payment. Decision and debit roll back together on failure. Reset requires the
literal RESET_WORKING_DATABASE and capability, preserves audit files, and
invalidates old requests. Do not reset during independent external MCP activity.

The API serializes mutations and rejects them during a live agent run. Its
reload lifecycle cancels jobs and closes the shared MCP client. Historical audit
remains; in-memory job statuses do not. Fifteen disposable/offline integration
tests passed, and live read-only HTTP endpoints were checked. No real payment,
purchase, reset, or live AI run was performed. This supersedes the earlier
statement that purchase order recording is absent; confirmed receipt and bulk
customer acceptance remain unmodeled.


### Completed-open run correction
See output/completed_open_investigation.md for actual evidence. Progress runs prepare known linked obligations through audited MCP Workflow calls, never approve them. Investigation mode disables preparation. GET /runs recovers recent outcomes from audit history and excludes runs predating the latest reset; GET /runs/{id} flags reset-invalidated historical runs. Dashboard offers Prepare payment request and explicit Continue ticket after human decisions, with actual outcome summaries. Rent preparation is allowed before its recorded due date. Business gaps do not justify invented stock receipts, supplier IDs or discount policies.

Follow-up: paid invoices no longer expose Prepare payment request; continuation remains separate from fulfillment. Default prompts are ticket-specific. Same-run specialist findings for the same role/topic are reused, with a delegation_reused audit entry; successful MCP mutations invalidate that cache. Token limits remain 40,000, with explicit UsageLimitExceeded messages. See output/post_payment_investigation.md.


### Business resolution workflows (implemented; not executed live)
See output/resolution_workflow_review.md for source facts, exact payment approval evidence and proposed completion rules. New table resolution_reviews stores kind, payload, pending/approved/denied/executed status, named approval and dates. Agent-visible prepare_resolution_review reads tickets, pricing, invoices, vendors, payments and prepares a non-payment proposal. Human-only decide_resolution_review accepts stated scope; pricing approval writes a conditional quote and resolves only the pricing request. advance_simulation_date explicitly changes desk date. confirm_simulated_receipt_and_fulfill validates approved simulation, lead time and paid vendor, then records classroom-only receipt/fulfillment atomically and marks the simulated order complete. Neither creates payments nor claims physical delivery.
Routes: POST /tickets/{id}/resolution/prepare; POST /tickets/{id}/resolution/{review}/decision; POST /simulation/date; POST /tickets/{id}/resolution/{review}/simulated-receipt. All mutation routes require human bearer authentication; decision/date/receipt tools require the backend-only MCP capability. GET /tickets/{id} includes resolution_reviews. Dashboard proposal review requires explicit assumption/completion-rule acknowledgement, separate clock confirmation and receipt confirmation. Original assignment policy/authority was not present; these are proposed rules requiring human/instructor acceptance, not discovered facts. Live tickets 101/103 remain open.

Accepted preparations are documented in output/prepared_decisions_review.md. New human-only record_conditional_quote_decision and POST /tickets/{id}/resolution/{review}/record-quote-decision record the named choice and a fresh-stock conditional quote while leaving the ticket open. Applying the pricing-only criterion is separate and preserves quote caveats. The accepted101 simulation plan does not advance the clock, receive stock or make a payment. Both101/103 remain open.

Final actual completion evidence: output/resolved_tickets.md and resolution_completion_evidence.json. All three working DB tickets are resolved after explicit user-confirmed workflows.101 receipt/fulfillment is SIMULATION ONLY dated2026-09-05;103 is pricing-only at58 with an unsent availability-conditional quote. Shared desk.date_today advanced to September5; original DB, payments and checking160 are unchanged. Criteria are not instructor-confirmed. Screenshot artifacts are linked in resolution_completion_manifest.json; older blocked runs remain historical audit evidence.


Runtime verification: get_runtime_identity reads SQLite database_list and exposes actual path/PID through GET /health. Human-only POST /recovery/committed-resolution calls recover_committed_resolution with human capability and expected reset sequence. It corroborates preserved completion against audit and checks cash, paid obligations, stock and pricing before restoring erased records. No payment or stock operation is replayed; agents cannot approve recovery. Result 1491 restored authorized completion after resets 1352/1454/1472. Current outcome reads actual ticket rows; historical attempts and technical JSON are collapsed; four completion stages are distinct. See output/discrepancy_investigation.md for current actual evidence and classroom limitations.
