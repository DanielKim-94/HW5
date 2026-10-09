# Problem 2: Campus Customs database harness

## Source and preservation

Source: `data/campus_customs.db`, inspected using SQLite in read-only mode. Working copy: `data/campus_customs_new.db`, a byte-for-byte copy. No business records were changed.

Inspection used `sqlite_master`, `PRAGMA table_info`, `PRAGMA foreign_key_list`, and the stored rows. Nine user tables were found. `PRAGMA integrity_check` returned `ok`; `PRAGMA foreign_key_check` returned no violations.

Original and initial working-copy SHA-256: `23686a90d698f7fa6f901a3f0a9774db9cbb31e13151c9e5717275f3321f360a`.

## Actual tables and fields

Types below are SQLite declared types. Required means an explicit NOT NULL constraint. PK denotes the primary key. SQLite reports no explicit NOT NULL for the INTEGER primary keys or the TEXT primary keys in cash_accounts/pricing; INTEGER PRIMARY KEY supplies the row identifier, while those TEXT primary keys do not independently prohibit NULL in this schema. All fields have no declared default.

### cash_accounts

Available cash for affordability checks. The only row is checking, balance 3400.0, dated 2026-08-31.

| Field | Type | Constraints | Meaning / uncertainty |
| --- | --- | --- | --- |
| `name` | TEXT | PK position 1 | Account identifier/name. |
| `balance` | REAL | NOT NULL | Recorded account balance; currency is unspecified. |
| `date` | TEXT | NOT NULL | Date associated with the balance; exact snapshot semantics are unspecified. |

### desk

Business-date context for agents. The one row sets date_today to 2026-08-31; notes is NULL. This is the database scenario date, not the computer date.

| Field | Type | Constraints | Meaning / uncertainty |
| --- | --- | --- | --- |
| `date_today` | TEXT | NOT NULL | Scenario/business date. |
| `notes` | TEXT | Nullable | Optional desk notes. |

### inventory

Stock by product and size, with a physical location. Agents can compare requested quantities with stock; there are 10 rows.

| Field | Type | Constraints | Meaning / uncertainty |
| --- | --- | --- | --- |
| `sku` | TEXT | NOT NULL, PK position 1 | Product identifier. |
| `name` | TEXT | NOT NULL | Product display name. |
| `size` | TEXT | NOT NULL, PK position 2 | Size code; OS appears for caps and mugs but is not defined. |
| `qty` | INTEGER | NOT NULL | Recorded stock quantity; reservation semantics are unspecified. |
| `location` | TEXT | NOT NULL | Physical storage location. |

The composite primary key is `(sku, size)`: sizes of the same SKU are separate stock rows.

### invoices

Vendor bills, amounts, due dates, and status. Agents can inspect obligations and connect bills to vendors. The only invoice is 501.

| Field | Type | Constraints | Meaning / uncertainty |
| --- | --- | --- | --- |
| `id` | INTEGER | PK position 1 | Invoice identifier. |
| `vendor_id` | INTEGER | NOT NULL | Vendor identifier; declared foreign key to vendors.id. |
| `amount` | REAL | NOT NULL | Invoice amount; currency unspecified. |
| `due_date` | TEXT | NOT NULL | Recorded due date. |
| `status` | TEXT | NOT NULL | Invoice state; only open is observed, allowed states are unspecified. |
| `description` | TEXT | Nullable | Optional invoice description. |

### leases

Rent obligations and landlord details. Agents can inspect the shop rent and its next due date. There is one lease.

| Field | Type | Constraints | Meaning / uncertainty |
| --- | --- | --- | --- |
| `id` | INTEGER | PK position 1 | Lease identifier. |
| `space_name` | TEXT | NOT NULL | Name of rented space. |
| `landlord` | TEXT | NOT NULL | Landlord name. |
| `monthly_rent` | REAL | NOT NULL | Monthly rent amount; currency unspecified. |
| `next_due` | TEXT | NOT NULL | Next rent due date. |
| `notes` | TEXT | Nullable | Optional lease notes. |

### payments

Payment records, including account and approver, for checking prior payments and recording future payments. Currently empty; no payment workflow is specified.

| Field | Type | Constraints | Meaning / uncertainty |
| --- | --- | --- | --- |
| `id` | INTEGER | PK position 1 | Payment identifier. |
| `kind` | TEXT | NOT NULL | Payment category; allowed values unspecified. |
| `ref_id` | INTEGER | Nullable | Optional referenced record identifier; target table unspecified. |
| `amount` | REAL | NOT NULL | Payment amount; currency unspecified. |
| `account` | TEXT | NOT NULL | Account name; no foreign key declared. |
| `paid_at` | TEXT | NOT NULL | Payment time/date text; format unspecified because the table is empty. |
| `approved_by` | TEXT | NOT NULL | Approver text; no identity or approval rules specified. |

### pricing

One cost and list price per SKU, shared across sizes. Agents can assess proposed prices against recorded costs. There are four rows.

| Field | Type | Constraints | Meaning / uncertainty |
| --- | --- | --- | --- |
| `sku` | TEXT | PK position 1 | Product identifier; no foreign key declared. |
| `unit_cost` | REAL | NOT NULL | Recorded per-unit cost. |
| `list_price` | REAL | NOT NULL | Recorded list price. |

### tickets

The work queue: request details, optional product or obligation references, status, notes, and creation time. All three rows are open.

| Field | Type | Constraints | Meaning / uncertainty |
| --- | --- | --- | --- |
| `id` | INTEGER | PK position 1 | Ticket identifier. |
| `type` | TEXT | NOT NULL | Request category; observed customer_order, rent_notice, price_override. |
| `requester` | TEXT | NOT NULL | Requester name/text; no customer table. |
| `subject` | TEXT | NOT NULL | Short request subject. |
| `sku` | TEXT | Nullable | Optional product identifier; no foreign key declared. |
| `size` | TEXT | Nullable | Optional size. |
| `qty` | INTEGER | Nullable | Optional requested quantity. |
| `lease_id` | INTEGER | Nullable | Optional lease reference; declared foreign key to leases.id. |
| `invoice_id` | INTEGER | Nullable | Optional invoice reference; declared foreign key to invoices.id. |
| `status` | TEXT | NOT NULL | Ticket state; only open is observed, allowed transitions unspecified. |
| `notes` | TEXT | Nullable | Optional free-text request details. |
| `created_at` | TEXT | NOT NULL | Creation timestamp; existing rows include the -04:00 offset. |

### vendors

Supplier directory with specialty and recorded lead time. Agents can inspect the vendor linked to an invoice. There are three rows.

| Field | Type | Constraints | Meaning / uncertainty |
| --- | --- | --- | --- |
| `id` | INTEGER | PK position 1 | Vendor identifier. |
| `name` | TEXT | NOT NULL | Vendor name. |
| `specialty` | TEXT | NOT NULL | Recorded specialty. |
| `lead_days` | INTEGER | NOT NULL | Recorded lead time in days; business/calendar days and start event are unspecified. |

## Relationships

Declared foreign keys (all use NO ACTION for updates and deletes):

- `tickets.invoice_id -> invoices.id`
- `tickets.lease_id -> leases.id`
- `invoices.vendor_id -> vendors.id`

Matches supported by existing values but not enforced as foreign keys:

- `(tickets.sku, tickets.size)` matches `(inventory.sku, inventory.size)`.
- `tickets.sku` and `inventory.sku` match `pricing.sku`.
- A payment account could match `cash_accounts.name`, but payments is empty and has no declared relationship.
- `payments.kind` plus `ref_id` might identify an obligation, but the database does not define that convention.

## The three open tickets

### Ticket 101: Bulldog tee

- Type: `customer_order`; requester: Tauhid Zaman; created: `2026-08-31T09:15:00-04:00`.
- Request: 1 `CC-TEE-WHITE`, size S. Notes: "Needs a tee in size S."
- Matching inventory: Classic Bulldog Tee, S, qty 0, Aisle B. The recorded stock is one unit short of the request.
- Matching pricing: unit_cost 8.0, list_price 28.0.
- Declared link: invoice_id 501 -> invoice amount 840.0, due `2026-08-28`, status `open`, description "Rush reprint CC-TEE-WHITE S".
- Invoice vendor_id 1 -> Bulldog Print Co, specialty apparel reprint, lead_days 5.
- The invoice is three calendar days past its due date relative to desk.date_today. Its description mentions the same product and size, but no structured invoice-line table identifies the reprint quantity.
- lease_id is NULL. Checking cash is relevant context for a possible payment, but there is no direct ticket-to-account link. Paying the invoice, delivery timing, and stock replenishment behavior are not defined by this database.

### Ticket 102: Rent due

- Type: `rent_notice`; requester: Elm City Properties; created: `2026-08-31T11:05:00-04:00`.
- Notes: "Email: shop rent due in 2 days."
- Declared link: lease_id 1 -> Chapel Street shop, landlord Elm City Properties, monthly_rent 2400.0, next_due `2026-09-02`, notes NULL.
- The next due date is two calendar days after desk.date_today, consistent with the ticket note.
- sku, size, qty, and invoice_id are NULL; there is no product or invoice link.
- Checking balance 3400.0 is relevant to affordability, and payments contains no recorded payments. There is no declared lease-to-payment relationship or evidence of an actual rent payment.

### Ticket 103: Bulk hoodie discount

- Type: `price_override`; requester: Yale AI Club; created: `2026-08-31T16:55:00-04:00`.
- Request: 20 `CC-HOOD-NAVY`, size M. Notes: "Student org wants 20 hoodies, size M, asking for a bulk discount."
- Matching inventory: Basic Hoodie Big Yale, M, qty 8, Aisle A. Recorded stock is 12 units short. Other sizes do not satisfy a size-M request without a changed request.
- Matching pricing: unit_cost 22.0, list_price 58.0. For 20 units, arithmetic at these recorded rates is 440.0 cost and 1160.0 list-price total; these are not approved quotes or all-in costs.
- lease_id and invoice_id are NULL. There is no structured SKU-to-vendor mapping identifying a hoodie supplier.
- No requested discount amount, minimum margin, approval policy, restock commitment, or customer deadline is stored.

## Unclear or absent information

- Currency is not recorded. Monetary values use REAL, with no rounding or monetary precision policy.
- Dates are TEXT; no date-format constraints are declared. Use the stored scenario date for this exercise unless instructed otherwise.
- No CHECK constraints define valid statuses/types, positive quantities/amounts, or nonnegative balances/stock.
- No customer, order-line, invoice-line, purchase-order, reservation, shipment, discount-policy, or agent tables exist. Free-text notes do not establish missing policies.
- payments is empty. Its kind/ref_id convention and account relation must be defined before relying on them.
- Cash of 3400.0 versus recorded rent 2400.0 and invoice 840.0 leaves 160.0 by arithmetic alone. This does not establish which payments to make, approval, other obligations, or available/reserved cash semantics.
- Foreign-key enforcement is a per-connection setting; declared relationships alone do not prove that future writers enable it.

The schema and ticket inspection above was completed in Problem 2. No ticket decisions were made.


# Problem 3: Shared FastMCP server

Implemented in `mcp_server/server.py`. Every HW5 agent will use this server's
shared tools. It targets only `data/campus_customs_new.db` using a path based on
the server file, not the launch directory. SQLite connections use `mode=ro`
and `query_only`, with each tool reading within one transaction snapshot.
Only three functions are registered as MCP tools; helpers remain internal.

| Tool | Ticket | Tables read | Why useful |
| --- | --- | --- | --- |
| `get_customer_order_context(ticket_id=101)` | 101 | tickets, inventory, pricing, invoices, vendors, desk, cash_accounts | Combines the size-S tee request with its stock and price, follows its declared invoice/vendor links, and supplies date/cash context to investigate the supply and invoice blocker. |
| `get_rent_payment_context(ticket_id=102)` | 102 | tickets, leases, desk, cash_accounts, invoices, payments | Combines the rent notice with the actual lease/due date, cash, competing open invoices, and payment history so agents can investigate timing and affordability. |
| `get_bulk_pricing_context(ticket_id=103)` | 103 | tickets, inventory, pricing | Combines the requested medium-hoodie quantity with exact-size availability and recorded cost/list price, exposing the stock shortage and pricing facts needed before considering a discount. |

## Return and error behavior

- Returns actual complete database rows as JSON-serializable dictionaries; no seeded answers or hardcoded stock, prices, dates, balances, or invoice amounts.
- Product lookups use ticket SKU/size. Invoice/vendor and lease lookups follow stored references. Every ID/value query uses SQL parameters.
- Missing tickets and mismatched ticket types raise clear errors. Missing related records return `null`; empty collections return `[]`. A missing database fails rather than creating a blank file.
- The rent tool returns all payments without asserting a lease association, because the database does not define `kind`/`ref_id`. It returns invoices whose stored status is `open`; these do not establish every obligation.
- The bulk tool also returns all sizes for the same SKU as context, without treating other sizes as substitutes.
- Each response flags relevant missing policies or relationships. The tools do not make decisions, modify data, approve payments, or promise delivery.

## Validation and next stage

Python syntax and the three decorated tool definitions were checked statically.
The original and working database hashes remain identical to the Problem 2
baseline. Dependencies are listed in `mcp_server/requirements.txt`; dependency
installation, MCP connection, runtime tool calls, and protocol testing are
reserved for Problem 4. No server was started or connected in Problem 3.

Implementation follows the [official FastMCP quickstart](https://github.com/PrefectHQ/fastmcp/blob/main/docs/getting-started/quickstart.mdx).


# Problem 4: Connection and smoke testing

## Configuration

- Workspace `.mcp.json` now contains `campus-customs`, preserving existing entries.
- Workspace `.codex/config.toml` contains the equivalent project-local stdio definition.
- The installed Codex CLI did not list the project-local definition. The workspace trust keys observed in user configuration contain a different/garbled path spelling; whether that caused the missing entry is unclear.
- Registered the same server using `codex mcp add campus-customs -- <HW5 venv Python> <server.py>`. `codex mcp get campus-customs --json` confirmed it is enabled with the correct absolute paths in the user's Codex configuration.
- Installed FastMCP 3.4.8 into the existing HW5 virtual environment. The initial install failed because sandbox networking blocked PyPI; the approved retry succeeded. The sandboxed Codex CLI also could not resolve its home directory; normal user execution succeeded.

## Actual protocol results

`mcp_server/smoke_test.py` launched the configured server as a subprocess using
stdio MCP, initialized a client, discovered exactly three tools, and called each
with its ticket ID. This was an assistant-operated protocol test, not a native
model tool invocation. Actual complete outputs, tool names, arguments, issues,
and row comparisons are saved in `output/mcp_smoke.json`.

All returned database rows matched independent read-only SQLite queries against
`data/campus_customs_new.db`, including complete ticket/stock/pricing records,
invoice/vendor for 101, lease/accounts/open invoices/payments for 102, and all
hoodie sizes for 103. Both database hashes were unchanged after the test. The
client closed its stdio server process when the test finished.

## Remaining assistant-native verification

The current conversation's exposed tool catalog does not contain campus-customs;
saving configuration does not add tools to an already-running chat. No native
assistant call is recorded as successful. The JSON marks this stage pending.
Restart the MCP connection in the coding assistant (Codex IDE: gear menu > MCP
servers > Restart extension; desktop: Settings > MCP servers > Restart), then
check `/mcp` or the server list for campus-customs. Project-local configuration
requires a trusted project; the user-level registration is also available.

Use these prompts in the refreshed assistant and append its actual native tool
results to the smoke record, comparing them with the working database:

1. Call the campus-customs MCP tool get_customer_order_context with ticket_id=101 and return its complete actual output. Do not resolve the ticket.
2. Call the campus-customs MCP tool get_rent_payment_context with ticket_id=102 and return its complete actual output. Do not resolve the ticket.
3. Call the campus-customs MCP tool get_bulk_pricing_context with ticket_id=103 and return its complete actual output. Do not resolve the ticket.

These are prepared prompts, not claimed user prompts already used. Only the
actual Problem 4 request is recorded in `AI_prompts.md`.

Configuration/restart reference: [official OpenAI MCP documentation](https://learn.chatgpt.com/docs/extend/mcp?surface=cli).


# Problem 5: Agent team and operational MCP

## Roles and implementation

| Agent | Prompt file in backend/prompts/ | Responsibility |
| --- | --- | --- |
| Boss | boss.md | Coordinate one ticket, reconcile evidence, surface human decisions |
| Inventory | inventory.md | Exact-size stock, vendor blockers and lead times |
| Accounting | accounting.md | Cash-out obligations, approvals, payment and pricing arithmetic |
| Facilities | facilities.md | Lease, landlord notice, rent dates |
| Customer Service | customer_service.md | Truthful unsent message drafts and missing customer requirements |

`backend/models.py` defines typed role/report/delegation/limit/decision contracts.
`backend/agents.py` constructs five PydanticAI agents and audits graph iteration.
`backend/tools.py` binds shop tools and delegation to one ticket;
`backend/audit.py` preserves audit entries; `backend/cli.py` exposes trusted local
commands. Every production AI call uses exactly `gpt-6.1-luna` through
`https://api.portkey.ai/v1` with `PORTKEY_API_KEY` from the root .env/environment.
This is the user's updated model requirement; no fallback model/provider.
Only an offline FunctionModel simulator may override the production factory.
No live Portkey availability test or ticket-resolution run was made in Problem 5.

All shop reads and operational changes go through MCP; production backend
code does not query SQLite. The backend launches the same MCP server with a
random human capability supplied only to its subprocess environment. The model
never receives it. Agent-accessible tools exclude human decision/setup methods.

## Tools and tables

The original three context tools remain with the reads described in Problem 3.
There are now **14 MCP tools: 12 agent-accessible tools and 2 human-only tools**.

| Added tool | Tables read | Tables written | Ticket and purpose |
| --- | --- | --- | --- |
| get_ticket_context | tickets, desk, extension tables when initialized | None | All: current ticket/date/operational evidence |
| get_vendor_shipping_status | tickets, vendors, invoices, desk | None | 101/103: all open bills and recorded lead time |
| request_payment_approval | tickets, invoices or leases, cash_accounts, payment_approvals, desk | payment_approvals | 101 invoice / 102 rent: pending human request for stored amount |
| get_payment_approval | payment_approvals | None | 101/102: durable decision details |
| execute_approved_payment | tickets, payment_approvals, cash_accounts, invoices or leases, payments, desk | cash_accounts, payments, payment_approvals, tickets; invoices or leases | 101/102: atomically record approved cash-out payment |
| save_message_draft | tickets, desk | message_drafts | All: unsent customer/vendor/landlord draft |
| save_quote_draft | tickets, pricing, desk | quote_drafts | 103: ticket price proposal without global pricing/revenue changes |
| plan_vendor_shipment | tickets, vendors, invoices, desk | shipment_plans | 101/103: draft plan, blocked by unpaid invoices |
| fulfill_customer_order | tickets, inventory, fulfillments, desk | inventory, fulfillments, tickets | 101: exact-size stock decrement and resolution, no revenue |
| initialize_shop_tools | sqlite schema | Extension tables and triggers | Human-only setup through MCP |
| record_human_payment_decision | payment_approvals, desk | payment_approvals | Human-only approve/deny; cannot be called by an agent |

## Actual extension fields

These tables were initialized in the working copy through MCP, not direct
backend SQL. The nine original tables' business rows remain unchanged. The
original DB still matches its Problem 2 SHA-256. Extension tables are empty
in the actual working copy; only disposable test copies contain test actions.

### payment_approvals

| Field | Type | Constraints |
| --- | --- | --- |
| `id` | TEXT | PRIMARY KEY |
| `ticket_id` | INTEGER | NOT NULL |
| `kind` | TEXT | NOT NULL |
| `ref_id` | INTEGER | NOT NULL |
| `amount` | TEXT | NOT NULL |
| `account` | TEXT | NOT NULL |
| `due_date` | TEXT | NOT NULL |
| `requested_on` | TEXT | NOT NULL |
| `status` | TEXT | NOT NULL |
| `approved_by` | TEXT | Nullable |
| `decision_on` | TEXT | Nullable |
| `payment_id` | INTEGER | Nullable |
| `reason` | TEXT | NOT NULL |

Foreign keys: payment_id -> payments.id; account -> cash_accounts.name; ticket_id -> tickets.id.

### message_drafts

| Field | Type | Constraints |
| --- | --- | --- |
| `id` | TEXT | PRIMARY KEY |
| `ticket_id` | INTEGER | NOT NULL |
| `recipient` | TEXT | NOT NULL |
| `body` | TEXT | NOT NULL |
| `created_on` | TEXT | NOT NULL |
| `status` | TEXT | NOT NULL, DEFAULT 'draft' |

Foreign keys: ticket_id -> tickets.id.

### quote_drafts

| Field | Type | Constraints |
| --- | --- | --- |
| `ticket_id` | INTEGER | PRIMARY KEY |
| `sku` | TEXT | NOT NULL |
| `size` | TEXT | NOT NULL |
| `qty` | INTEGER | NOT NULL |
| `unit_price` | TEXT | NOT NULL |
| `unit_cost_snapshot` | TEXT | NOT NULL |
| `rationale` | TEXT | NOT NULL |
| `created_on` | TEXT | NOT NULL |
| `status` | TEXT | NOT NULL, DEFAULT 'draft' |

Foreign keys: ticket_id -> tickets.id.

### fulfillments

| Field | Type | Constraints |
| --- | --- | --- |
| `ticket_id` | INTEGER | PRIMARY KEY |
| `sku` | TEXT | NOT NULL |
| `size` | TEXT | NOT NULL |
| `qty` | INTEGER | NOT NULL |
| `fulfilled_on` | TEXT | NOT NULL |

Foreign keys: ticket_id -> tickets.id.

### shipment_plans

| Field | Type | Constraints |
| --- | --- | --- |
| `id` | TEXT | PRIMARY KEY |
| `ticket_id` | INTEGER | NOT NULL |
| `vendor_id` | INTEGER | NOT NULL |
| `sku` | TEXT | NOT NULL |
| `size` | TEXT | NOT NULL |
| `qty` | INTEGER | NOT NULL |
| `planned_on` | TEXT | NOT NULL |
| `earliest_arrival` | TEXT | NOT NULL |
| `evidence` | TEXT | NOT NULL |
| `status` | TEXT | NOT NULL, DEFAULT 'draft' |

Foreign keys: vendor_id -> vendors.id; ticket_id -> tickets.id.


Payment kinds are constrained to invoice/rent; approval status to
pending/approved/denied/executed. Draft status is always draft. Quote,
fulfillment, and shipment quantities are positive. All declared extension
foreign keys use NO ACTION. Amount strings are validated with Decimal; the
original monetary columns remain REAL. Two triggers reject negative/increased
cash on updates and negative inventory on updates.

## Business safeguards

- Shop date comes from exactly one valid desk.date_today row; vendor estimates use actual nonnegative lead_days. Any open unpaid invoice blocks shipment planning, not just overdue bills. No shipment is actually dispatched.
- A payment request cannot pay. An agent cannot approve, assert a human identity, or supply a capability. The trusted human CLI requires an explicit approve/deny decision. This trusts a local OS operator; the name is asserted, not a remotely authenticated identity. Future backend routes must authenticate and authorize humans server-side.
- Approvals bind ticket, invoice/lease reference, amount, account, and due date. Execution rechecks cash and unchanged obligation under BEGIN IMMEDIATE. Insufficient cash refuses requests and execution; no negative balance or revenue is allowed.
- One transaction inserts payments, debits cash/account date, marks the invoice paid OR advances lease next_due, annotates the ticket, and marks approval executed. Rent payment resolves its rent ticket; invoice payment leaves the order open. Replays return the same payment without charging again. An approved but unexecuted stale request can be revoked by human denial and replaced.
- New explicit convention: payments.kind=invoice/ref_id=invoices.id or kind=rent/ref_id=leases.id; the original schema did not define it. payment_approvals adds exact due-date/payment linkage.
- Rent recurrence is an implementation convention: one calendar month from the previous due date, clamped at month end. Vendor date arithmetic uses calendar days and is labeled unconfirmed; original lead_days business/calendar-day semantics remain unknown.
- Quotes/messages/shipment plans stay unsent drafts. No global price change, stock reservation, incoming cash, customer/vendor contact, or fabricated delivery occurs. Below-cost quote drafts are rejected as a conservative added safeguard, not an original policy. Supplier evidence is supplied text and is not independently verified.
- Exact-size customer-order fulfillment is atomic/idempotent and refuses insufficient stock. No confirmed-delivery/restock tool is implemented, so out-of-stock tickets cannot be completed by inventing stock. Bulk customer acceptance/discount approval/final fulfillment remains unmodeled.

## Delegation and usage limits

Any starting agent can delegate to any other relevant role on the same ticket.
Target role/topic and ticket category are validated; self/active-ancestor cycles
are rejected. Semantic relevance also depends on prompts and audit review:
structural topic membership does not prove free-text tasks are relevant.
Delegates share dependencies, MCP, and usage, with fresh message histories.
There is no forced tour of all five agents.

Defaults across the full delegation tree: 12 model requests; 30 successful
PydanticAI tool calls including delegation, plus at most 30 MCP attempts;
24,000 provider-reported total tokens; 1,500 output tokens per model request;
60 graph nodes; 8 delegations; depth 3; 180 seconds per ticket. SDK retries are
off; one corrective PydanticAI retry is allowed. Tool timeout is 45 seconds,
MCP timeout 30 seconds. Token usage is checked from reports after responses,
so the final response can cross the total threshold. These are usage caps,
not guaranteed dollar costs. Top-level runs in a team serialize; SQLite
transactions protect payment changes across processes. Budget stops are audited.

## Audit and validation

Each actual node start/completion/failure, model response, delegation,
operational MCP call/result, approval request, and human decision/payment event
is appended to output/audit_trail.json with ticket, agent, run ID, timestamp,
and sequence. Complete operational results are retained. No private reasoning,
API keys, or human capabilities are logged. Existing entries are preserved by
file locking and atomic replacement; malformed logs fail without overwrite.
Database commits and audit writes are separate transactions: after a crash,
reconcile with durable approval/payment records. The real audit currently
records actual schema initialization only. Simulated runs use disposable logs.

Nine offline integration tests passed: approval/capability gate, insufficient
cash at request/execution, changed obligations/reapproval, idempotent and
concurrent payment replay, vendor shipping block/lead time, rent updates,
draft/stock checks, delegation/loop limits, and prior audit entry preservation.
All use disposable databases and an offline FunctionModel, with no live AI or
real shop payments. Actual read-only stdio MCP discovery found 14 tools and
verified current ticket contexts and unchanged original business rows;
evidence is in output/team_validation.json. All three real tickets remain open.

See backend/README.md for run and trusted human CLI commands. Backend routes,
dashboard, ticket planning, and resolution are later problems. The prior
Problem 4 native-assistant verification remains pending; protocol testing
alone is not a native model tool call.

References: [PydanticAI delegation](https://pydantic.dev/docs/ai/guides/multi-agent-applications/),
[agent iteration and limits](https://pydantic.dev/docs/ai/core-concepts/agent/),
[compatible providers](https://pydantic.dev/docs/ai/models/compatible-apis/),
[Portkey gateway examples](https://github.com/Portkey-AI/portkey-python-sdk).

# Problem 6: Reviewed ticket plans

The user reviewed the proposed plans for tickets 101, 102, and 103 and approved
them with “use this plan.” They are saved in `output/desk_tickets.html`, a
self-contained local HTML page with ticket, Cash, and Reflection tabs.

Boss contacts Inventory first for 101 (no size-S tee stock), Facilities first
for 102 (verify the lease/rent date), and Inventory first for 103 (12 medium
hoodies short). The Expected sections include specialist-to-specialist
handoffs, conditional MCP tools, reasoning, approval boundaries, and expected
stopping points. Actual sections are empty; Cash and Reflection are placeholders.

The agreed plan identifies a proposed `get_cash_obligations(ticket_id)` tool
for same-ticket access to competing obligations. It remains unimplemented in
this planning stage. Confirmed-delivery/restock and bulk acceptance/fulfillment
remain gaps; no fabricated stock or resolution is expected. No agent execution,
payment, customer/vendor contact, or operational data change was made here.


# Problem 7: FastAPI dashboard backend

Implemented in `backend/main.py` with a lifespan-managed shared MCP connection.
It supports imports both as backend.main and as main from backend/. Model
construction remains lazy; server startup and read routes make no live AI calls.

## Routes and purpose

| Method | Route | Purpose | Human bearer token |
| --- | --- | --- | --- |
| GET | /health | Backend readiness and current active run ID | No |
| GET | /tickets | The three assignment tickets and current stored statuses/date, via MCP | No |
| GET | /tickets/{ticket_id} | Ticket context, drafts, approvals, purchases and fulfillment evidence via MCP | No |
| POST | /tickets/{ticket_id}/run | Start the selected role/team on this ticket; return 202 and run_id | Yes |
| GET | /runs/{run_id} | Poll queued/running/completed/failed/interrupted run status and result | No |
| GET | /activity | Recent actual audit events, agent messages/model responses, tool calls/results and approvals; filter by ticket_id/run_id and paginate with after_sequence/limit | No |
| GET | /cash | Actual checking balance and its date from MCP; currency remains unspecified | No |
| GET | /approvals | Stored payment and purchase requests; optional ticket_id filter, including denied/executed history | No |
| POST | /tickets/{ticket_id}/payments/prepare | Create/reuse a pending invoice/rent payment for the exact stored obligation; never spend | Yes |
| POST | /tickets/{ticket_id}/purchases/prepare | Create/reuse a pending exact-product purchase using recorded cost and supplied supplier evidence; never spend or receive stock | Yes |
| POST | /approvals/{approval_id}/approve | Human approve=true decision; atomically verify and execute the prepared payment/purchase through MCP | Yes |
| POST | /approvals/{approval_id}/deny | Human denial/revocation of an unexecuted request through MCP; no spending | Yes |
| POST | /reset | Restore working DB from original using MCP SQLite backup; reinitialize empty operational tables, preserve audit | Yes |
| GET | /docs, /redoc, /openapi.json | Interactive/API schema documentation | No |

Ticket routes accept only 101, 102, or 103. Mutation bodies forbid extra fields.
Preparation does not accept an arbitrary payment amount: invoice/rent amounts
come from their linked DB records. Approval accepts only ticket ID, request type,
human name, and explicit approve=true; the stored request controls amount,
account, product/reference, and quantity. Invalid/missing identity or input is
rejected. Missing/invalid human token returns 401; unknown ticket/request 404;
stale/denied/insufficient/blocked/conflicting operations return 409.

## Human boundary and transaction safeguards

A random human API bearer token is stored in ignored `backend/.human_api_token`,
or supplied by CAMPUS_HUMAN_API_TOKEN (at least 32 characters). It persists
across reload and is never exposed by an endpoint, prompt, audit, or agent tool.
In /docs, use Authorize with this local token. All POST routes require it.
Read routes are intended for a local dashboard; they are not authenticated.
The human name is asserted by the bearer-authorized local operator, not a
multi-user identity service. Do not expose this development backend publicly.

The API keeps the separate MCP human capability server-side. Approval/reset
MCP tools are excluded from the agent allowlist. An agent has no HTTP, filesystem,
API-token, or human-capability tool. Preparation cannot cause approval. Human
approval and spending occur in one BEGIN IMMEDIATE transaction: verify a pending
request, recheck unchanged obligation/cash, update approval, debit cash, insert
payment, and update invoice/lease/ticket records. Failure rolls back the decision
and debit together. Executed requests return their original payment on replay;
SQLite locking also protects concurrent attempts. Agents cannot self-approve.

A purchase is also a prepared cash-out action, bound to SKU/size, vendor, qty,
recorded unit_cost, account, and recorded lead time. One pending/executed purchase
per ticket is enforced by a partial unique index. Quantity cannot exceed the
recorded shortage. Execution rejects changed facts, insufficient cash, or ANY
open unpaid invoice for that vendor. It inserts purchases/payment records and
annotates the ticket, but leaves stock unchanged and the ticket open. Expected
arrival uses vendor lead_days from desk.date_today as unconfirmed calendar-day
arithmetic. Supplier evidence and the use of recorded unit_cost as a purchase
price are explicit assumptions for human review, not verified supplier quotes.
No vendor contact, incoming cash, or receipt is modeled.

## MCP additions and schema

New tools: list_shop_tickets, get_checking_balance, get_cash_obligations,
list_approval_requests, request_purchase_approval, approve_and_execute_payment,
approve_and_execute_purchase, deny_prepared_request, reset_working_database.
The agreed Problem 6 same-ticket cash-obligation gap is now implemented.
There are 23 MCP tools: 15 agent-accessible, 2 dashboard-wide read tools, and
6 human-only administrative tools. Original context and operational tools remain.

Read-only additions use tickets, desk, cash_accounts, invoices, leases, payments
and approval records. Purchase preparation reads tickets, inventory, pricing,
vendors, cash_accounts and desk, then writes purchase_approvals. Purchase execution
also reads invoices and atomically writes purchase_approvals, purchases, payments,
cash_accounts and ticket notes. Human payment execution shares the existing
payment logic; it now combines decision and execution in one transaction.
Reset restores all working tables from the read-only original and recreates
operational extensions; it never clears output/audit_trail.json.

### purchase_approvals fields

| Field | Type | Constraints |
| --- | --- | --- |
| `id` | TEXT | PRIMARY KEY |
| `ticket_id` | INTEGER | NOT NULL |
| `vendor_id` | INTEGER | NOT NULL |
| `sku` | TEXT | NOT NULL |
| `size` | TEXT | NOT NULL |
| `qty` | INTEGER | NOT NULL |
| `unit_cost` | TEXT | NOT NULL |
| `amount` | TEXT | NOT NULL |
| `account` | TEXT | NOT NULL |
| `requested_on` | TEXT | NOT NULL |
| `lead_days_snapshot` | INTEGER | NOT NULL |
| `supplier_evidence` | TEXT | NOT NULL |
| `status` | TEXT | NOT NULL |
| `approved_by` | TEXT | Nullable |
| `payment_id` | INTEGER | Nullable |

Foreign keys: payment_id -> payments.id; account -> cash_accounts.name; vendor_id -> vendors.id; ticket_id -> tickets.id.

### purchases fields

| Field | Type | Constraints |
| --- | --- | --- |
| `id` | INTEGER | PRIMARY KEY |
| `approval_id` | TEXT | NOT NULL |
| `ticket_id` | INTEGER | NOT NULL |
| `vendor_id` | INTEGER | NOT NULL |
| `sku` | TEXT | NOT NULL |
| `size` | TEXT | NOT NULL |
| `qty` | INTEGER | NOT NULL |
| `unit_cost` | TEXT | NOT NULL |
| `amount` | TEXT | NOT NULL |
| `ordered_on` | TEXT | NOT NULL |
| `earliest_arrival` | TEXT | NOT NULL |
| `status` | TEXT | NOT NULL, DEFAULT 'ordered' |

Foreign keys: vendor_id -> vendors.id; ticket_id -> tickets.id; approval_id -> purchase_approvals.id.


Purchase approval status is pending/denied/executed; purchases status is ordered.
Quantity must be positive; purchases.approval_id is unique. New payment convention:
kind=purchase, ref_id=purchases.id. No received-stock claim is implied.

## Runs, reset, and audit limits

Only one dashboard agent run is active at a time. Other mutation routes return
409 during a run, preventing reset or payment from invalidating active reasoning.
Read/activity routes remain available while the agent runs. All existing shared
agent request/token/delegation/time limits still apply, and all production calls
remain gpt-6.1-luna through Portkey. Background jobs live in this server process;
reload cancels an active job, audits interruption, and closes the MCP subprocess.
Run-status memory is lost on restart, but durable audit and approval records remain.
There is no durable task queue or automatic restart/re-execution of an interrupted
model run. Live Portkey/model availability has not yet been tested.

The reset endpoint requires the literal RESET_WORKING_DATABASE and human token,
refuses while a run is active, clears pending requests/operational records by
restoring the original, and then reinstalls the operational schema. It preserves
the audit and invalidates old approval IDs; historical payment entries remain in
audit but no longer represent the reset scenario. Backup and extension recreation
are separate phases; startup initialization can repair an interrupted recreation.
Independent external MCP clients are outside the API's single-run lock.

Backend calls append request/result/failure and approval events to the existing
audit, omitting human capabilities and API credentials. /activity reads this
actual log; it does not fabricate messages. Cursor requests return the next page;
initial requests return the most recent page. File locks protect concurrent access.

## Startup and verification

From HW5/backend, activate the existing venv and run the requested command:

```powershell
..\.venv\Scripts\Activate.ps1
uvicorn main:app --reload --port 8000
```

Equivalent without activation:

```powershell
..\.venv\Scripts\python.exe -m uvicorn main:app --reload --port 8000
```

The backend was started in a hidden process with that equivalent command and
verified on http://127.0.0.1:8000. Swagger docs: http://127.0.0.1:8000/docs.
The reloader process tree PID/command is saved in output/backend_process.json;
logs are output/backend_stdout.log and output/backend_stderr.log. When stopping,
terminate the entire recorded process tree, not only the port listener. Uvicorn
reload is enabled as explicitly requested; the project's Dash-specific no-reloader
rule does not apply to this FastAPI backend.

Fifteen integration tests passed: the nine existing MCP/team safeguards plus six
HTTP-to-MCP tests covering authentication, preparation/execution separation,
wrong-ticket/replayed approvals, insufficient cash/stale-data atomic rollback,
purchase shipping/cash/stock/idempotency, background run/activity, reset and audit
preservation. Tests use disposable DBs and an offline FunctionModel only.
Live read-only HTTP checks passed for health, tickets, cash, approvals, and activity;
output/backend_smoke.json records them. All real tickets are still open, checking
is 3400, and no real payment/purchase was prepared or executed. The original hash
and original nine-table records are unchanged. No live model run or real reset
was invoked in this stage.

References: [FastAPI lifespan](https://fastapi.tiangolo.com/advanced/events/),
[Uvicorn development settings](https://www.uvicorn.org/settings/).

## Problem 8: Agent dashboard

## Problem 9 investigation and clean-run preparation

Model clarification follow-up: all five agents now use the assignment's exact
gpt-6-luna via Portkey with Chat Completions reasoning_effort none. Both actual
function-call and PydanticAI typed-output probes returned gpt-6-luna-2026-09-22.
Safe headers show azure-openai, config.targets[2], zero retries. The available
key cannot read gateway configs (403 AB03), so the historical rule that selected
5.6 remains unverified. HTTP request/response audit hooks now check every response
and reject a different/missing model before tools. Twenty-two offline tests pass.
See output/model_and_business_review.md, model_routing_checks.json,
agent_model_verification.json, portkey_config_access.json, and business_evidence.json.
Older model references below describe historical implementation and are superseded
by this clarification; original prompt/audit records are not rewritten.

No independent HW5 assignment handout was found locally; data.zip contains only
the original DB. Ticket 101 has zero exact-size stock and no receipt workflow;
paying its invoice does not resolve it. Ticket 103 has neither authorized discount
terms nor a price-override approval/resolution workflow. Neither can legitimately
resolve with the current information/tools. Ticket 102 can resolve upon actual
human-approved rent payment. Keep blocked results distinct from resolved status.

Actual first clean run: ticket 101, run 0e62cad3-f4cc-42c5-b8b5-e9bd83ffc7a7,
audit sequences 200–292. Boss asked Inventory for stock/vendor evidence and then
Accounting for invoice preparation; Inventory did not perform the planned direct
Accounting handoff. Nine real model responses all reported
gpt-6-luna-2026-09-22. Invoice request 1a09a940-c9d3-4763-b089-4e9a9274870f
is pending for 840; no payment executed, checking 3400, ticket open. The runner
stopped at awaiting_human. No clean 102/103 run or resolution screenshot yet.
Current Actual/Cash and run_evidence.json reflect these records. Earlier run/reset
descriptions below are preserved historical checkpoints, not current status.

Failed database/audit/log copies and hashes are preserved in
output/diagnostics/20261009T040935Z. See output/investigation.md for ticket-specific
sequence references, recovered tool-validation errors, terminal failures, and
unverified causes. No diagnostic copy was reset.

Audit replacement now retries transient Windows access-denied failures without
truncation. Exact MCP argument fields are loaded into agent instructions and
validated before calls. Prompts avoid unchanged repeated lookups. Current limits
are 20 requests and 40,000 reported tokens, superseding the earlier 12/24,000
defaults. A pending approval now ends the run with awaiting_human immediately;
the human must decide externally before a new continuation run. A resolved
report requires an MCP ticket status check. Returned live model names are audited
and must match the selected configured model before response tools execute.

Eighteen offline tests pass, including transient/persistent audit replacement
and pending-approval pause with zero payment execution. Completion of future
live runs is not inferred from offline tests.

The authorized reset succeeded through POST /reset after preservation and tests.
output/clean_run_manifest.json records clean batch
clean-1db1d5aa-f3a3-4710-9ace-ffd718ca9d0b, baseline checking 3400, open tickets,
and a verified hash of the earlier 191 audit entries. A clean_batch_started audit
event separates this reset baseline from previous attempts. New live runs have
not started pending clarification of the provider model discrepancy and real
stock/pricing evidence. No payment was approved during investigation.

Follow-up: the top-right **Reset working database** button calls authenticated
POST /reset with confirmation RESET_WORKING_DATABASE only after the human
confirms in a dialog. Active runs disable it; the backend independently enforces
the same restriction. Success clears cached jobs and reloads actual shop records
while retaining audit history. Seven browser tests and the production build passed,
including mock reset success/refusal. No reset of the real database was performed.

frontend/ contains a React/Vite/TypeScript dashboard at http://localhost:5174,
connected to http://localhost:8000. Port 5173 is occupied by Lecture 12 and was
left running. Backend CORS includes localhost and 127.0.0.1 on 5174.
POST /session/verify validates the human bearer token without changing records.

The dashboard uses GET /tickets, /cash, /approvals, /health, /activity and
/runs/{run_id}; POST /tickets/{ticket_id}/run starts the selected ticket;
POST /approvals/{id}/approve or /deny records the explicit human decision.
Approval remains separate from preparation. All operational changes still go
through the backend's MCP tools. The UI never infers resolution from a completed
agent run and refreshes authoritative checking cash after payment.

Activity polls every two seconds and displays actual messages, delegations,
tool requests/results, and errors. Five role cards summarize recorded contributions.
Human credentials are memory-only. Loading, stale/disconnected, refusal, and
empty states are explicit. Browser activity is capped at 1,000 events per ticket;
the audit file preserves full history. Layout and creative choices are documented
in output/design.md; startup and tests in frontend/README.md.

The production build and five browser tests passed. Browser actions used mock
HTTP fixtures, while the display test read the live backend. Screenshots are
output/dashboard_desktop.png and output/dashboard_mobile.png. No real agent run
or financial operation was executed during frontend testing.


### Completed-open run correction
See output/completed_open_investigation.md for actual evidence. Progress runs prepare known linked obligations through audited MCP Workflow calls, never approve them. Investigation mode disables preparation. GET /runs recovers recent outcomes from audit history and excludes runs predating the latest reset; GET /runs/{id} flags reset-invalidated historical runs. Dashboard offers Prepare payment request and explicit Continue ticket after human decisions, with actual outcome summaries. Rent preparation is allowed before its recorded due date. Business gaps do not justify invented stock receipts, supplier IDs or discount policies.

Follow-up: paid invoices no longer expose Prepare payment request; continuation remains separate from fulfillment. Default prompts are ticket-specific. Same-run specialist findings for the same role/topic are reused, with a delegation_reused audit entry; successful MCP mutations invalidate that cache. Token limits remain 40,000, with explicit UsageLimitExceeded messages. See output/post_payment_investigation.md.

Latest review: output/current_ticket_blockers.md documents post-reset-814 runs. Human review distinguishes no pending spending approvals from business decisions; blocked summaries/next actions remain visible. Paid invoice reports are reconciled against actual executed approval records to replace stale approval-pause text.


### Business resolution workflows (implemented; not executed live)
See output/resolution_workflow_review.md for source facts, exact payment approval evidence and proposed completion rules. New table resolution_reviews stores kind, payload, pending/approved/denied/executed status, named approval and dates. Agent-visible prepare_resolution_review reads tickets, pricing, invoices, vendors, payments and prepares a non-payment proposal. Human-only decide_resolution_review accepts stated scope; pricing approval writes a conditional quote and resolves only the pricing request. advance_simulation_date explicitly changes desk date. confirm_simulated_receipt_and_fulfill validates approved simulation, lead time and paid vendor, then records classroom-only receipt/fulfillment atomically and marks the simulated order complete. Neither creates payments nor claims physical delivery.
Routes: POST /tickets/{id}/resolution/prepare; POST /tickets/{id}/resolution/{review}/decision; POST /simulation/date; POST /tickets/{id}/resolution/{review}/simulated-receipt. All mutation routes require human bearer authentication; decision/date/receipt tools require the backend-only MCP capability. GET /tickets/{id} includes resolution_reviews. Dashboard proposal review requires explicit assumption/completion-rule acknowledgement, separate clock confirmation and receipt confirmation. Original assignment policy/authority was not present; these are proposed rules requiring human/instructor acceptance, not discovered facts. Live tickets 101/103 remain open.

Accepted preparations are documented in output/prepared_decisions_review.md. New human-only record_conditional_quote_decision and POST /tickets/{id}/resolution/{review}/record-quote-decision record the named choice and a fresh-stock conditional quote while leaving the ticket open. Applying the pricing-only criterion is separate and preserves quote caveats. The accepted101 simulation plan does not advance the clock, receive stock or make a payment. Both101/103 remain open.

Final actual completion evidence: output/resolved_tickets.md and resolution_completion_evidence.json. All three working DB tickets are resolved after explicit user-confirmed workflows.101 receipt/fulfillment is SIMULATION ONLY dated2026-09-05;103 is pricing-only at58 with an unsent availability-conditional quote. Shared desk.date_today advanced to September5; original DB, payments and checking160 are unchanged. Criteria are not instructor-confirmed. Screenshot artifacts are linked in resolution_completion_manifest.json; older blocked runs remain historical audit evidence.


Runtime verification: get_runtime_identity reads SQLite database_list and exposes actual path/PID through GET /health. Human-only POST /recovery/committed-resolution calls recover_committed_resolution with human capability and expected reset sequence. It corroborates preserved completion against audit and checks cash, paid obligations, stock and pricing before restoring erased records. No payment or stock operation is replayed; agents cannot approve recovery. Result 1491 restored authorized completion after resets 1352/1454/1472. Current outcome reads actual ticket rows; historical attempts and technical JSON are collapsed; four completion stages are distinct. See output/discrepancy_investigation.md for current actual evidence and classroom limitations.
