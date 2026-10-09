# Resolution review, current evidence and unfinished assignment

Implementation success is not ticket resolution. Actual status: 101 open, 102 resolved, 103 open. No further live resolution, simulation clock advance, receipt, payment or reset was executed during this review.

## Preservation and supplied materials

Before changes: diagnostics/20261009T062242Z/campus_customs_new.db and audit_trail.json, plus full records.json and hashes in manifest.json. Original data.zip contains only data/campus_customs.db. Workspace search found no separate HW5 assignment handout/scenario document. User prompts and original database are supplied evidence; generated harness/plans are not independent assignment instructions. Instructor intent cannot be verified without the actual scenario. In particular, a receipt or pricing policy need not pre-exist: they may be records/workflows the assignment expects us to create.

## Current checking reconciliation

Baseline 3,400.00 after latest recorded reset at audit 1075. Current payments:

|Payment|Ticket|Obligation|Amount|Human evidence|Result|
|---|---|---|---:|---|---|
|1|101|invoice 501|840.00|Dawon Kim; executed approval 8824006a-65c0-4d1d-9f47-3001905d6a39; authenticated human approval call 1157 at 2026-10-09 06:20:05 UTC, result 1158|checking 2,560; invoice paid; ticket stays open|
|2|102|lease 1 rent|2,400.00|Dawon Kim; executed approval 50aca65d-ec67-414c-bfe7-4922a5f5dd0c; authenticated human approval call 1238 at 2026-10-09 06:20:26 UTC, result 1239|checking 160; ticket resolved|

3,400 ? 840 ? 2,400 = 160. No other current payments, incoming cash, purchase approvals or pending spending approvals. Database currency is unspecified; USD comes from the user's description. Named audit calls and durable records prove the approval workflow ran; we cannot independently identify the person holding the token.

## Historical payments are not additional current debits

All successful execution results retained in the audit are listed below, separated by resets. Payment IDs restart after a reset. Earlier runs must not be summed into the current balance.

- Audit 657, 2026-10-09T05:30:52.685962+00:00: ticket 101, payment 1, 840.0, approved_by Dawon Kim, request 0f37d0f8-53f2-4581-a259-4f799c290ade; historical prior-reset batch.
- Audit 661, 2026-10-09T05:31:07.600306+00:00: ticket 102, payment 2, 2400.0, approved_by Dawon Kim, request e68b8e92-92b5-46c5-a27f-3f713d290d30; historical prior-reset batch.
- Audit 897, 2026-10-09T06:10:36.327685+00:00: ticket 101, payment 1, 840.0, approved_by Dawon Kim, request 69a9bac8-39a2-429c-854c-d28691e8a656; historical prior-reset batch.
- Audit 978, 2026-10-09T06:11:02.241149+00:00: ticket 102, payment 2, 2400.0, approved_by Dawon Kim, request 2fb986a7-fabc-4c0b-b7fe-90d231698061; historical prior-reset batch.
- Audit 1158, 2026-10-09T06:20:05.095680+00:00: ticket 101, payment 1, 840.0, approved_by Dawon Kim, request 8824006a-65c0-4d1d-9f47-3001905d6a39; CURRENT database batch.
- Audit 1239, 2026-10-09T06:20:26.969462+00:00: ticket 102, payment 2, 2400.0, approved_by Dawon Kim, request 50aca65d-ec67-414c-bfe7-4922a5f5dd0c; CURRENT database batch.

## Ticket 102: actual resolution

Working DB status is resolved, notes: ?Email: shop rent due in 2 days. Rent payment 2 recorded with human approval.? Payment 2 and executed request match audit 1239. Lease 1 next_due is now 2026-10-02 (the implemented monthly advance convention), rent remains 2,400. desk.date_today remains 2026-08-31. This is actual recorded resolution evidence, not just a completed agent job. No resolved dashboard screenshot was newly captured in this review.

## Ticket 101

Original full notes: ?Needs a tee in size S.? Ticket requests one CC-TEE-WHITE S and links invoice 501. Invoice original description is ?Rush reprint CC-TEE-WHITE S?, vendor 1 Bulldog Print Co, specialty apparel reprint, lead_days 5, amount 840, originally open due 2026-08-28, now paid. That explicit description is genuine vendor/SKU/size evidence; previous statements treating all supplier linkage as missing were too broad. Stock S is zero (M5/L3/XL2 are not substitutes); unit_cost8, list28.

Missing source facts: invoice line quantity, shipping confirmation, receipt date/quantity, and whether lead_days means calendar/business days or starts on payment. Not missing: linked reprint vendor or its lead time.

Missing implementation before this change: an explicitly labeled simulation proposal, acceptance of assumptions, simulated time advance, simulated receipt and fulfillment. Existing tools could only plan a draft shipment and fulfill already-recorded stock; that prevented completing the simulated chain.

Implemented now: prepare_resolution_review(kind=simulated_restock) reads paid linked invoice and real vendor lead time, proposes exactly the requested one tee (explicit assumption, not an invoice quantity fact) and September 5 as calendar-day arrival from August 31 payment. Human decision approves only the plan. Separate trusted clock advance and human simulated-receipt confirmation can atomically record simulated receipt/fulfillment and resolve, with SIMULATION ONLY notes, replay protection, no cash change and no physical delivery claim. No tool executes before human acknowledgement; receipt is rejected before desk date reaches the planned arrival. Current exact blocker: acceptance of classroom simulation assumptions/completion rule. Concrete next step: choose the simulation proposal or ask instructor to confirm it. No live proposal or assumption has been accepted yet.

## Ticket 103

Original full notes: ?Student org wants 20 hoodies, size M, asking for a bulk discount.? Type price_override, requester Yale AI Club, SKU CC-HOOD-NAVY, qty20 M. Pricing cost22/list58; stock M8, S4/L14/XL6. Vendor1 apparel reprint/5days; vendor2 mugs and small goods/3days; vendor3 local courier/1day. No original hoodie SKU/vendor agreement or supplier commitment is recorded. Vendor specialty alone does not establish a specific supplier contract.

Missing source facts: mandated discount, delegated pricing authority and intended completion criterion; supplier commitment if we claim fulfillment. A policy is not inherently required to propose and record a human-authorized one-off decision. No physical fulfillment is implied by a price_override ticket.

Missing implementation before this change: human authorization of a one-off price, a conditional quote completion workflow and a durable pricing-decision record. Existing save_quote_draft stored only a draft and had no resolution path; our prompts also incorrectly treated absence of an existing discount policy as barring any proposal.

Implemented now: prepare_resolution_review(kind=pricing_decision) creates a reviewable price proposal at/above recorded cost (our safeguard, not an original policy); human must expressly accept quote-only completion. Approval saves an UNSENT conditional quote with stock/supply caveats, records named authorization and resolves the price question only. No revenue, purchase, stock decrement, supplier fact, customer acceptance or full-order fulfillment is claimed. Global list pricing is unchanged. Current exact blocker: selecting/authorizing a price and accepting that this price_override is complete with an unsent conditional response. Concrete options: propose50 (13.79% below58,28 above22, total1,000), decline discount/retain58 (total1,160), or obtain instructor-required pricing/resolution rule. The full 20 cannot currently be fulfilled: shortage12; a hypothetical12?22=264 exceeds cash160, and recorded cost is not a supplier quote. A conditional pricing response need not procure those units.

## Instructor questions if the proposed rules are not acceptable

1. For 101, should paid reprint invoice501 be treated as authorizing simulated restock of the ticket quantity, with calendar-day lead time and a simulated clock/receipt? If not, what quantity/date or alternative completion evidence is required?
2. For 103, may Boss/human choose a one-off price and resolve the price_override with an unsent availability-conditional quote, or must20 units actually be supplied? What discount/margin authority or supplier evidence is required if so?

## Routes and practical boundaries

POST /tickets/{id}/resolution/prepare ? non-payment proposal only.
POST /tickets/{id}/resolution/{review}/decision ? named human accepts/rejects stated completion rule; pricing approval can complete only the pricing ticket, restock approval leaves order open.
POST /simulation/date ? trusted human explicitly advances classroom desk date with reason, not historical payment dates or real time.
POST /tickets/{id}/resolution/{review}/simulated-receipt ? separate explicit human simulated receipt and fulfillment after lead time, never physical delivery.

Agents may prepare proposals but have no access to decision, clock or receipt capabilities. Dashboard offers proposal preparation, displays payload/assumptions, requires human acknowledgement, and confirms simulation clock/receipt separately. Non-payment resolution reviews are intentionally distinct from spending approvals.

## Validation versus completion

30 offline backend tests passed, including human-only authorization, preparation leaving tickets open, lead-time refusal, explicit simulation, replay protection, conditional pricing with no cash/stock changes, and schema/API safety. Production build and nine browser tests passed, including explicit pricing-scope acknowledgement. These are implementation checks on disposable data. They are not evidence that 101 or103 is currently resolved; both remain open pending the specific decisions above.
