# Completed but open: actual-run investigation

Evidence preserved before fixes: diagnostics/20261009T051535Z (SQLite backup, 651 audit entries, logs, raw records, API responses and hashed manifest). User screenshots depict unresolved runs; attached bytes were not available as local files. They are not resolution evidence.

The previous pending invoice request 1a09a940-c9d3-4763-b089-4e9a9274870f was genuinely created at sequence 287. The subsequent dashboard reset succeeded at sequence 295, deleting working approvals without making payment and preserving audit history. The evidence identifies a reset-route action, not the identity of the person who clicked it.

## Ticket 101

Run `5cbf5332-10f2-485e-9056-468dc0b467f1`. Boss told Accounting not to request payment unless directly required (351); Accounting explicitly prepared none (375). Inventory found zero size-S stock; no genuine receipt is recorded. Customer Service saved an unsent draft. Final report was draft_ready (434), not resolved.

## Ticket 102

Run `de013ccb-a656-48d7-9ec9-5d86ee01d389`. Facilities invented a restriction against preparation before the due date (472). Boss explicitly prohibited Accounting from requesting payment (481). Final report claimed awaiting_human but contained no approval IDs (511). No request was created. Preparation before September 2 is supported.

## Ticket 103

Run `66a28ddf-4f5c-4e3e-bf7c-79cb0d3c130d`. Eight size-M hoodies cannot cover twenty. No supplier association or discount policy/authority is provided. Two invented vendor ID 0 lookups failed (582,632). Final report was blocked (651). No purchase or payment request was created.

## Agreement across records

Database and captured API agree: three open tickets, no payments, no payment/purchase approval records, checking 3,400. The latest runs never called request_payment_approval/request_purchase_approval. Their zero approval count is not a frontend filter problem. ?Run completed? described the job finishing, not business resolution. Old pre-reset evidence must not be represented as current requests.

## Fixes and next steps

Prompts explicitly require relevant Accounting preparation, including advance rent review. Progress runs have an audited Workflow fallback reading fresh MCP records and preparing a known linked unpaid obligation when cash permits; it cannot approve. Investigation-only checkbox disables preparation. Existing pending requests are reused; denied obligations are not automatically recreated. Dashboard provides Prepare payment request, accurate outcome/summary/next actions, durable run recovery, and Continue ticket after a human decision. A prepared payment pauses model work; continuation is an explicit new run with fresh MCP facts. The reset dialog counts pending requests it removes. Invalid vendor IDs are rejected before MCP.

For 101, human approval may pay invoice 501 (840) and unblock vendor shipping, but is not stock receipt. Legitimate fulfillment still needs real receipt evidence and an authorized MCP receipt-recording workflow; no receipt is invented. For 102, prepare rent (2,400), review and approve or decline. Approved rent can legitimately resolve 102. Both payments total 3,240 leaving 160; preparation does not debit cash. For 103, obtain an actual supplier/lead time/cost for the missing twelve hoodies and a human-authorized unit price or actual discount rule plus quote completion criteria. Current tools cannot establish that missing policy or complete an unsupported price override. No tickets were forcibly resolved.

Verification: 26 offline backend tests passed, including future-due rent preparation, no-preparation mode, durable run recovery, approval replay protection and cash safeguards. Production TypeScript/Vite build passed. No live model requests, payments, reset or ticket reruns were made for these checks. Model remains gpt-6-luna through Portkey.

Dashboard verification: all eight browser tests passed (including manual preparation and explicit post-approval continuation) after restoring the backend. The backend runs without the reloader to avoid interrupted development processes. Live API verification is saved in post_fix_api_verification.json.
