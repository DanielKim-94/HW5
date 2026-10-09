# Failed-run investigation

Current follow-up status: the required gpt-6-luna is verified through actual
Portkey/PydanticAI response metadata. All five agents use it with fail-closed
model checks; 22 offline tests pass. Only clean ticket 101 has run and is paused
for human approval of invoice 501 for 840, with checking unchanged at 3400.
See model_and_business_review.md for exact model, routing, receipt, policy,
and assignment-material findings. Older sections below document the investigation
and reset state at the time they were recorded; their pending model clarification
has now been answered by the user and verified.

Diagnostic snapshot: output/diagnostics/20261009T040935Z. The working DB was copied using SQLite backup, the audit under its file lock, and backend logs were copied before any reset/rerun. manifest.json records SHA-256 hashes; database_records.json contains the actual snapshot rows; run_summary.json indexes relevant events. The original DB hash remains 23686a90d698f7fa6f901a3f0a9774db9cbb31e13151c9e5717275f3321f360a.

## Ticket 101

Run 8e99e05d-04ea-4058-baea-c823bdf20e3a, audit sequences 7–27, read the ticket and customer-order context. Sequence 26 records PermissionError / WinError 5 while replacing the audit JSON with its atomic temporary file; sequence 27 records dashboard failure. No fulfillment, payment, or approval is in the current snapshot. The error proves audit replacement failed, but does not identify the locking process. OneDrive/antivirus contention is a possible cause, not verified evidence.

## Ticket 102

Run 4cca7076-082d-450e-88ef-0bbc5a18e504, sequences 30–113. Facilities passed lease_id to a context tool that only accepts ticket_id (59–60), then corrected it (65–66). This was recovered, not the final failure. Accounting prepared rent request 918102f4-98a9-4f2e-a3ec-4f123fd0456e for 2400, pending human approval (93–94), then reread four unchanged contexts (99–106). At sequence 109, reported cumulative tokens reached 24,569 against the 24,000 limit. The error propagated to Boss and the dashboard (110–113). Facilities' earlier resolved report described its completed check, but the database ticket remained open. A later successful reset (114–115) removed the pending request; it was not paid.

## Ticket 103

Run b7e31d63-f4c6-42c1-a411-48082ac68724, sequences 116–190. Inventory verified 8 size-M hoodies against 20 requested, a shortage of 12, with no structured supplier mapping or restock commitment (156). Accounting verified unit cost 22 and list price 58 and correctly identified the missing discount policy (178). Boss reread context (184) and exceeded the 24,000-token limit at 27,679 (188–190). No quote/message draft, purchase, payment, or resolution is recorded.

## Current records and uncertainty

All three tickets are open. Checking is 3400 dated shop date 2026-08-31. payments, payment_approvals, purchase_approvals, purchases, quote_drafts, message_drafts, and fulfillments are empty. The audit contains successful resets after runs 101 and 102. This explains why current records differ from the historical pending rent request. No screenshot of those failed runs exists in the supplied evidence; earlier UI test screenshots do not document them.

Every recorded provider response names gpt-5.6-luna-2026-07-09, although config.py requested gpt-6.1-luna. The local evidence does not establish whether Portkey aliasing, key-level routing, or another upstream setting caused this. Model choice must be clarified before the clean run; a new guard will reject mismatched provider model names before executing response tools.

## Fixes and verified limits

- Audit replacement retries transient PermissionError under the existing file lock, retaining atomic replacement and never truncating the previous log. Persistent failures still surface.
- Agents receive actual MCP field contracts loaded from list_tools; extra/missing argument keys are rejected before MCP. Context tools require ticket_id only.
- Role prompts are shorter, discourage unchanged repeated reads, preserve all business safeguards, and specify useful specialist handoffs. Shared hard limits are now 20 model requests and 40,000 reported tokens; other bounds remain in RunLimits. This gives headroom without removing limits; completion of live runs remains unverified until they occur.
- A durable pending payment/purchase request stops the run immediately and produces an awaiting_human report without another model call. Approval remains external and human-only.
- A resolved report now requires a fresh MCP ticket-status check. Agent task completion is not ticket resolution.
- Eighteen offline integration tests passed, including transient/persistent audit-lock failures and automatic approval pause with zero payment execution. They use disposable DBs/FunctionModel, not fabricated live evidence.

The remaining business blockers are real: paying invoice 501 does not establish received size-S stock, and ticket 103 has no discount policy or verified supplier mapping. A full run may correctly stop blocked; resolution screenshots can only be captured once actual backend status is resolved. No stock receipt, policy, payment approval, or customer acceptance will be invented.

## Clean baseline established

After the fixes passed tests, the authorized POST /reset succeeded. Clean batch clean-1db1d5aa-f3a3-4710-9ace-ffd718ca9d0b is recorded in output/clean_run_manifest.json and a clean_batch_started audit entry. The earlier 191 entries were verified unchanged using a canonical JSON prefix hash. Checking is 3400 and all tickets are open. New live runs await model clarification. The real screenshot helper was exercised against ticket 101 and correctly refused to capture an open ticket; no fake resolved screenshot was produced.

output/desk_tickets.html Actual/Cash and output/run_evidence.json now distinguish failed attempts from this clean baseline. They will be refreshed after actual runs and human decisions. output/manage_clean_run.py can queue/status runs through the API but has no approval action. frontend/scripts/capture-ticket.mjs captures only genuinely backend-confirmed resolved dashboard pages. Diagnostic snapshots remain untouched.

Implementation references: [PydanticAI message history](https://pydantic.dev/docs/ai/core-concepts/message-history/) and [Portkey gateway](https://github.com/portkey-ai/gateway). Local audit and database records, not those references, establish the failures above.
