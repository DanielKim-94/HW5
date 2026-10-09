> Historical review: conclusions about missing receipt/policy workflows have been revised. Read [resolution_workflow_review.md](resolution_workflow_review.md) for the distinction between missing facts, implemented simulation/pricing paths and unaccepted completion rules.

# Required model and resolution evidence

## Requested model versus actual response

The earlier Problem 5 prompt recorded in AI_prompts.md explicitly specified gpt-6.1-luna. backend/config.py hard-coded that name; there was no local alternate-model fallback. The root agents.md separately specified gpt-5.6-luna, but that did not change this hard-coded value. The latest user clarification establishes **gpt-6-luna through Portkey for every agent** and supersedes those earlier model names. The historical prompt record remains unchanged.

Preserved audit responses report gpt-5.6-luna-2026-07-09 with provider_url https://api.portkey.ai/v1/ and provider_name openai. Those old events do not preserve outbound HTTP bodies or gateway routing headers, so the source code and response metadata establish a mismatch, but cannot prove which Portkey rule selected 5.6. No locally supplied x-portkey-config, virtual key, MODEL_NAME override, or fallback was found. The root .env has only PORTKEY_API_KEY.

Current verification:

- A minimal POST /chat/completions with model gpt-6-luna, function calling, and reasoning_effort none returned HTTP 200, model gpt-6-luna-2026-09-22, and a real function call. Response headers: x-portkey-provider azure-openai; x-portkey-last-used-option-index config.targets[2]; x-portkey-retry-attempt-count 0; cache MISS. IDs and sanitized request/response evidence are in model_routing_checks.json.
- The actual PydanticAI/OpenAI client configuration returned the same model snapshot and a valid typed output. agent_model_verification.json identifies all five configured agents as gpt-6-luna and stores actual request fields/response metadata. No shop facts were sent and no shop operation executed in either probe.
- GET /configs returned HTTP 403, code AB03, stating insufficient permissions. portkey_config_access.json preserves that response. Therefore the precise historic gateway matching/override/fallback rule remains **unverified**. Current response headers confirm a gateway config target is active, but not its full rules. The probes do not prove that no future gateway fallback exists.

backend/config.py now fixes gpt-6-luna for all agents and uses reasoning_effort none with Chat Completions. HTTP hooks record outbound model/settings and safe response routing headers per ticket/agent/run. They reject a different or missing returned model before the agent can execute response tools; only the exact alias or a dated gpt-6-luna snapshot is accepted. No alternate model or external routing setting was changed. Twenty-two offline tests passed, including correct metadata, wrong/missing metadata stopping before tools, audit reliability, approval pauses, and transactional safeguards.

The required model is currently available to this key via Portkey. Exact gateway rules require a config/log export or read permission from the Portkey account administrator, if a definitive explanation of the historic 5.6 selection is required.

## Assignment material boundary

The supplied HW5 data.zip contains only data/campus_customs.db. Read-only inspection of all nine original tables, exact ticket notes, and actual current MCP contexts is saved in business_evidence.json. No separate HW5 PDF, DOCX, notebook, or assignment handout was found in HW5 or the searched workspace. Available assignment directions are the user's recorded prompts and the approved Problem 6 plan. Their plans explicitly permit blocked stopping points. Generated harness/prompts are implementation documentation, not independent evidence of a shop rule. Materials not supplied cannot be verified.

## Ticket 101: what exists and what is missing

Original ticket 101 requests 1 CC-TEE-WHITE, size S, links invoice 501, and notes only “Needs a tee in size S.” Its exact inventory quantity is 0. Invoice 501 is open for 840 and describes “Rush reprint CC-TEE-WHITE S”; it links vendor 1, Bulldog Print Co, with lead_days 5. This is useful textual evidence linking the invoice/product/vendor, not receipt evidence. The invoice has no line-item quantity, shipment record, received date, or received quantity. No goods-receipt or supplier mapping table exists. Even 840 divided by unit_cost 8 cannot establish receipt quantity or that those costs apply to the invoice.

Payment tools can prepare and, after explicit human approval, pay invoice 501, decrement cash, and mark the invoice paid. They do not add stock or resolve ticket 101. plan_vendor_shipment creates an unconfirmed draft and does not receive goods. request_purchase_approval/approved purchase records cash-out and an order, not stock receipt. fulfill_customer_order requires adequate actual exact-size stock; it refuses this baseline.

**Cannot legitimately resolve now.** Missing: verified receipt/source evidence identifying actual SKU, size, quantity and date, plus a trusted MCP receipt/replenishment workflow before fulfillment. A forecast using desk date 2026-08-31 plus five calendar days gives an unconfirmed 2026-09-05 estimate, not proof that goods have arrived. No receipt, stock increment, size substitution, or successful outcome will be invented.

## Ticket 103: what exists and what is missing

Original ticket 103 is price_override: Yale AI Club requests 20 CC-HOOD-NAVY, size M, asking for a bulk discount. It records no proposed price or discount. Exact stock is 8, a shortage of 12; unit_cost 22 and list_price 58 are recorded. The original pricing table has only sku, unit_cost, list_price. There is no discount rate, minimum-margin policy, approval authority, customer deadline, accepted quote, or acceptance record. Vendor specialty “apparel reprint” does not independently establish a hoodie supplier.

save_quote_draft can save an unsent proposal and rejects below-cost prices as an implementation safeguard; it is not a human-approved policy. save_message_draft can save questions/terms. Neither updates the ticket status or records acceptance. The existing fulfill_customer_order tool accepts only customer_order tickets, not price_override. No price-override approval/resolution tool exists.

**Cannot legitimately resolve with current tools/information.** First clarify an authorized price/discount and approval authority, and whether “resolved” means an approved pricing decision or completed physical fulfillment. A pricing-decision outcome would need an explicit human-decision MCP workflow with evidence; physical fulfillment would additionally need verified supply/receipt of the missing size-M stock. A payment approval is not discount approval. Stock shortage does not by itself prevent a conditional draft quote, but such a draft is not resolution.

## Ticket 102 and next steps

Ticket 102 links lease 1 with monthly_rent 2400 due 2026-09-02. The human approval route can pay this actual obligation, insert its payment, debit checking, advance next_due under the disclosed calendar-month convention, and mark ticket 102 resolved. It is resolvable after human approval if enough cash remains. Paying invoice 840 and rent 2400 would leave 160 from the 3400 baseline; that is planning arithmetic, not an actual cash update.

Keep clean batch clean-1db1d5aa-f3a3-4710-9ace-ffd718ca9d0b. Work one ticket at a time without another reset. Stop on each real pending approval. Screenshot capture checks both API and dashboard resolved status and refuses open tickets. Original data and diagnostic files remain unchanged; new events append to the audit. Do not represent blocked or awaiting_human tickets as resolved.

References: [OpenAI GPT-6 API/tool compatibility](https://developers.openai.com/api/docs/guides/latest-model), [Portkey config defaults and overrides](https://portkey.ai/docs/product/ai-gateway/configs), [Portkey routing headers](https://portkey.ai/docs/api-reference/inference-api/headers). These describe API behavior; the saved local response metadata establishes this project's actual verification.

## First clean ticket run: actual pause

Only ticket 101 has started: run 0e62cad3-f4cc-42c5-b8b5-e9bd83ffc7a7.
The actual model_http_response audit entries all report gpt-6-luna-2026-09-22.
Accounting prepared invoice request 1a09a940-c9d3-4763-b089-4e9a9274870f for
840; the run stopped with awaiting_human (approval event 287, final report 292).
The request is pending, no payment has executed, checking is still 3400, and
ticket status remains open. No resolution screenshot exists. Tickets 102/103
have not started in this clean batch. The current status/Actual/Cash evidence is
in clean_run_manifest.json, run_evidence.json, and desk_tickets.html.
