# Post-payment investigation

Evidence preserved before fixes in diagnostics/20261009T053237Z: working SQLite backup, audit, backend logs, tickets/cash/approvals/runs API responses. User screenshots show review dialogs and open/failed states; they are not resolution evidence for 101 or 103.

## Ticket 101

No reopening occurred. It was open before and after payment. Approval 0f37d0f8-53f2-4581-a259-4f799c290ade executed invoice 501 payment 1 for 840 at audit sequence 657, reducing checking from 3,400 to 2,560. The payment result explicitly says fulfillment remains separate. Size-S stock is still zero; no receipt or fulfillment is recorded. Four subsequent human preparation attempts failed at 805/807/809/811 because invoice 501 was already paid. The refusal correctly prevented another request/payment. The dashboard should not have offered that button; it now hides preparation for executed linked invoices and explains the remaining stock/fulfillment blocker. Continue ticket reviews the evidence, but cannot invent a receipt or resolve absent stock.

## Ticket 102 and cash

Rent approval e68b8e92-92b5-46c5-a27f-3f713d290d30 executed payment 2 for 2,400 at sequence 661. Backend and DB confirm ticket 102 resolved and checking 160. Two payments total 3,240. Zero pending requests. This is actual approved cash-out evidence, not assumed arithmetic.

## Ticket 103

Run 382fce0f-a485-407a-bf3a-4b2b87411e02 failed at sequences 801?803: UsageLimitExceeded, total_tokens_limit 40,000, actual total_tokens 43,265. A shared limit is checked after a response, so the observed usage can exceed the threshold. It was not a paid-invoice error. Boss consulted Inventory, then Accounting repeated Inventory's stock check. Specialist findings already established 8 size-M hoodies against 20 requested (shortage 12), unit cost 22, list price 58, no discount authority and no supplier evidence. No purchase or quote was recorded; the ticket remains open. The screenshot's red paid-invoice error came from later ticket-101 manual actions and persisted across ticket selection.

## Fixes and verification

Paid linked invoices no longer expose Prepare payment request. Ticket switches clear prior action errors/notices. Default tasks now mention only the selected ticket. Specialist findings for the same role/topic are reused within a run; successful MCP mutations invalidate cached findings. Reuse is separately audited and does not make another AI call. Prompts instruct concise findings and stopping after necessary specialists. Token limits and gpt-6-luna remain unchanged; this reduces repeated work but is not proof of a successful future live run. Usage-limit failures expose their actual reason rather than a generic error. No automatic ticket rerun was performed.

The existing 26 backend tests passed, plus a new offline test verifying specialist reuse without another model call. TypeScript/Vite production build passed. Eight browser tests verify actual post-payment read-only records and mocked paid-invoice/continuation controls. No reset, payment, receipt, policy or forced resolution was introduced during investigation.

Next supported actions: 101 needs real receipt evidence and an authorized MCP receipt workflow before fulfillment. 103 needs a human-authorized price/discount decision and genuine supplier/availability evidence; with checking 160, replenishing twelve at recorded unit cost 22 would cost 264 before other costs, exceeding current cash. Unit cost is not a supplier quote, and no revenue may be added to cure this shortage. Human scope/fulfillment decisions or additional assignment evidence are required.
