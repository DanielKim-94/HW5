# AI Prompt Record

Record the prompts actually used for each problem. For follow-ups, include a short explanation of what was missing from the first result. Work only on the problem requested at each stage.

## Problem 1: Vibe coder prompts

### Prompt 1

```text
Great. Let's start a homework.
Unzip the data.zip in HW5 folder.
Also I want to keep a clear record of how I use AI throughout this assignment. Create `AI_prompts.md` with a section for each of the 11 problems.
For now, record this prompt under Problem 1 and leave the other sections ready for later. As we work through each problem, record the prompts I actually use. If I ask a follow-up, include it with a short explanation of what was missing from the first result. Please work only on the problem I ask about at each stage.

Use problems title below:
Problem 1: Vibe coder prompts
Problem 2: Study the Campus Customs database
Problem 3: Build the MCP server
Problem 4: Add the MCP server to vibe coder and test each tool
Problem 5: Build the agent team and grow the MCP tools
Problem 6: Plan the three tickets
Problem 7: Backend routes
Problem 8: Agent dashboard
Problem 9: Resolve the tickets
Problem 10: Reflection
Problem 11: Submit to GitHub
```

## Problem 2: Study the Campus Customs database

### Prompt 1

```text
Let's move to Problem 2.

I want to understand how the shop database works before building the agents.
Open`data/campus_customs.db`, walk me through every table and its fields, and explain how the three open tickets connect to the other tables?
Make a working copy called `data/campus_customs_new.db` and keep the original unchanged. Start `output/harness.md` with the actual fields in each table and a short explanation of why each table matters for the agents. Please use the database itself as the source and flag anything that is unclear rather than guessing.
```

## Problem 3: Build the MCP server

### Prompt 1

```text
Build a FastMCP server in mcp_server/ that uses data/campus_customs_new.db (do not need to connect or run it now).

Based on the tickets and database we inspected, choose and implement three tools that will help the agents make progress. Give each tool a clear name and return actual database information.
In output/harness.md, explain which tables each tool reads, which ticket it supports?101, 102, or 103?and why that particular tool is useful for that ticket. Also create a short mcp_server/READme.md explaining the server, its database, and its three tools. We will connect and test the server in the next problem.

Every agent in this HW uses the tools in this MCP server.
```

## Problem 4: Add the MCP server to vibe coder and test each tool

### Prompt 1

```text
I want to check that my coding assistant can actually call the MCP tools we built. 
Connect the server to this project and save the connection configuration in .mcp.json, or the equivalent local configuration required by my coding assistant.
Then help me test each of the three tools through the connected assistant. Save the prompt used, the tool name, and its actual output in output/mcp_smoke.json. Check that the returned values match data/campus_customs_new.db. If a connection or tool call fails, explain the issue and help me fix it before recording a successful test.
```

## Problem 5: Build the agent team and grow the MCP tools

### Prompt 1

```text
I want to build a team where each agent has a clear responsibility and can ask another agent for help when needed. Use PydanticAI to create five agents: Boss, Inventory, Accounting, Facilities, and Customer Service.

Put one prompt file per agent in backend/prompts/, shared data types in backend/models.py, and the agent implementation under backend/. Allow any agent to delegate to any other agent, while keeping delegation relevant to the ticket. All agent AI calls must use gpt-6.1-luna through Portkey with PORTKEY_API_KEY.

Please make the prompts specific to each role and cover the shop’s rules:

- Use desk.date_today as the shop’s current date.
- Use vendor lead times from the database.
- A vendor cannot ship while it has an open unpaid invoice.
- Every payment requires human approval.
- Refuse payments when cash is insufficient and never allow a negative balance.
- Update the relevant database records after an approved payment.
- Do not add revenue; this assignment only models cash going out.
- Keep customer messages as drafts without contacting real customers or vendors.

Expand the MCP server with the tools needed for the tickets. All shop facts and operational database changes should go through MCP.

Append each agent-loop step to output/audit_trail.json, including the ticket, agent, delegation, tool calls, results, and approval requests needed to understand the run. Preserve previous entries. Update the harness and MCP README with the agents, tools, tables, business safeguards, and practical limits on loops, delegation, and token use.
```

## Problem 6: Plan the three tickets

### Prompt 1

```text
Let's move to Problem 6.
Before running the team, I want to think through how each ticket should be handled. Could you walk me through tickets 101, 102, and 103 using the database information we have already inspected?
For each ticket, help me identify which agent the Boss should contact first and why, the expected delegations—including relevant specialist-to-specialist handoffs—and the MCP tools likely to be needed. Please explain the reasoning so I can review and adjust the plan.
After I review it, create output/desk_tickets.html as a page I can open directly, with separate tabs for the three tickets, Cash, and Reflection. Put the agreed plan in each ticket’s Expected section. Leave Actual empty, and leave Cash and Reflection as placeholders for later.
```

### Follow-up 1: Plan approval

```text
use this plan.
```

The first result provided the proposed plans and awaited the requested review before creating the HTML page. This follow-up approved those plans and authorized creating `output/desk_tickets.html`; it did not change the plan or authorize an agent run.

## Problem 7: Backend routes

### Prompt 1

```text
move to problem 7.

I want to connect the agent team to a dashboard. Could you build the FastAPI backend in `backend/main.py` with routes to:

- List the three tickets and their current status.
- Run the agent team on a selected ticket.
- Return recent agent messages and tool activity.
- Execute a prepared payment or purchase after a human approves it.
- Return the current checking balance.
- Reset the working database from the original.

Keep payment preparation separate from execution. The approval route should verify the pending request and available cash, prevent duplicate payments, and use MCP to make the database changes. Agents should never be able to approve their own payments.

Please list each route and its purpose in `output/harness.md`, and help me start the backend from `backend/` using `uvicorn main:app --reload --port 8000`.
```

## Problem 8: Agent dashboard

### Prompt 1

```text
I want the dashboard to feel like a clear, practical workspace for someone managing Campus Customs. Could you build it in `frontend/` using React, Vite, and TypeScript, connected to the backend at `http://localhost:8000`?
The dashboard should show all three tickets, let me select and run one, display each agent’s messages and actions as the run progresses, and summarize each agent’s contribution. Show the actual ticket status, pending payment or purchase requests with a human approval button, and the checking balance after approved payments.
I would like a clean Yale Blue theme, readable cards, and distinct visual cues for the five agents. Make pending approvals easy to notice and show loading or error states clearly. Only mark a ticket resolved when the backend confirms it.
Configure backend CORS for the Vite origin, help me start the dashboard with `npm run dev`, and write `output/design.md` explaining the layout and creative choices.
```

### Follow-up 1: Working database reset control

```text
Could you check whether the dashboard has a database reset button? If it does, tell me where it is. If it does not, add one connected to the backend reset route so I can restore the working database before the full three-ticket run.
```

The first dashboard included ticket runs and payment review but omitted a reset control. This follow-up adds a human-authenticated, explicitly confirmed button connected to POST /reset. Adding and testing the control did not reset the real database or start the three-ticket run.

## Problem 9: Resolve the tickets

### Prompt 1: Investigate failures and prepare an evidenced clean run

```text
All three ticket runs failed, and I did not take screenshots. Could you help me investigate what went wrong?
Before resetting or rerunning anything, preserve the current working database and audit trail as separate diagnostic copies. Check the backend logs, `output/audit_trail.json`, and the current ticket and payment records. Explain the failure for each ticket using the available evidence, and flag anything you cannot verify.
Fix the underlying issues and verify the relevant steps. Then help me reset the working database for a clean three-ticket run. Keep the earlier audit entries and clearly distinguish the new run.
During the new run, pause for my payment approvals and help me capture an actual dashboard screenshot after each ticket is resolved. Use only the real run evidence to update the Actual and Cash sections and the required output files.
```


### Follow-up 1: Required model and legitimate resolution evidence

```text
The assignment specifies `gpt-6-luna` through Portkey for every agent. Please check why the code requested `gpt-6.1-luna` and why Portkey reported `gpt-5.6-luna`. Verify the configured model and routing against the actual response metadata. Do not switch to another model without asking me. If the required model is unavailable, explain the blocker before starting another full run.
For ticket 101’s missing stock-receipt evidence and ticket 103’s missing discount policy, please check the original database, ticket details, and assignment materials. Explain exactly what is missing and whether each ticket can be legitimately resolved with the available tools and information. Do not invent a receipt, policy, or successful outcome.
Keep the clean baseline and preserved diagnostic records. Once these issues are clarified, help me run one ticket at a time, pause for my payment approvals, and capture screenshots only after the backend confirms resolution.
```

The first investigation left the model requirement ambiguous and did not independently verify the required model's actual Portkey response. This follow-up fixes the target to gpt-6-luna, requests routing metadata checks and a precise boundary on missing receipt/policy evidence, and authorizes sequential runs after clarification. Earlier failed responses and prompts are preserved as historical evidence.

### Follow-up 2: Completed runs with unresolved tickets

```text
I ran all three tickets in the dashboard. Each says ?Run completed,? but all three remain Open. There are zero pending approvals, and checking is still 3,400.
Please inspect these actual runs and explain why each stopped without resolving the ticket. Compare the audit trail, database records, pending approval records, and the dashboard API responses.
You previously reported a pending approval for invoice 501 on ticket 101. Why is it no longer visible? For ticket 102, why was no rent approval presented? Check whether requests were never created, lost, or created but not displayed.
Fix any implementation issues preventing the agents from preparing requests, showing them to me, or continuing after approval. For business blockers, explain the supported next step and any decision you need from me. Do not invent stock receipts or discount policies, and do not force ticket statuses to Resolved.
Preserve this run?s evidence before any reset. These screenshots show completed runs with unresolved tickets; do not use them as resolved-ticket evidence.
```

Earlier work did not distinguish a completed agent job from resolution or explain the reset-deleted approval and absent new requests. This follow-up requests actual-run diagnosis, preparation/display/continuation fixes, and evidence preservation. Three supplied screenshots show open tickets, not resolutions.

### Follow-up 3: Invoice paid, ticket still open; ticket 103 failed

```text
101 is open again and 103 failed. check the problem
```

Four dashboard screenshots accompanied this prompt. Earlier fixes still exposed preparation for a paid invoice and repeated specialist work could exceed the shared token budget. This follow-up asks to check actual payment and run evidence.

### Follow-up 4: Make the remaining result and decisions clear

```text
Error is corrected. But 101 is still open after approving the request for 840 USD, and 103 also open and seems no result is came.(Nothing waiting on you) sentence is appeared. Check the problem and solve it.
```

The previous result did not make clear that no spending approvals is distinct from missing business decisions, and the approval-pause report stayed visible after payment. This follow-up asks to check and correct those gaps.

### Follow-up 5: Reconcile payments and implement supported business workflows

```text
The assignment is still incomplete. Please distinguish implementation fixes and passing tests from actual ticket resolution. A successful run ending in Blocked does not satisfy the requirement to resolve all three tickets.

Before making further changes, reconcile the checking balance from 3,400 to 160. List every payment, its ticket, amount, and actual human approval evidence. Also report ticket 102?s current database status and resolution evidence.

For tickets 101 and 103, distinguish:

1. Facts genuinely missing from the supplied assignment data.
2. Workflows or MCP tools we have not implemented.
3. Business decisions the assignment allows the Boss or me to make.

Review the full ticket notes, relevant database rows, vendor records, pricing, and assignment scenario. Do not assume that a receipt or discount policy must already exist in the original database. Determine whether the assignment expects us to implement a simulated restocking workflow or make and record a supported business decision.

Implement the missing workflows supported by the assignment. Label simulation assumptions explicitly, and do not invent supplier facts or claim physical delivery occurred. If you need a decision from me, ask a specific question with the available options and consequences rather than saying ?business decision needed.?

Preserve the current database and audit evidence. Do not reset, make additional payments, or force tickets to Resolved. Report each ticket?s current status, exact blocker, and concrete next step. If the supplied materials truly make resolution impossible, identify the precise missing information so I can ask the instructor.
```

Earlier results conflated missing pre-existing policy/receipt facts with missing implementation and made all supplier linkage appear absent. This prompt requests scenario-based workflow review, exact payment reconciliation, explicit simulations and concrete human choices. Attached screenshot is open/blocked evidence, not proof of resolution.

### Follow-up 6: Accept simulation preparation and retain list price

```text
For ticket 101, first confirm whether the one-tee classroom simulation requires any additional purchase or payment beyond the paid invoice. Explain the basis for the quantity and the September 5 receipt date, including which date starts the five-day lead time.
If no additional payment is required, I accept calendar days and a clearly labeled classroom simulation assumption. Prepare the simulated receipt step for my separate confirmation; do not record it yet or present it as actual delivery.
For ticket 103, retain the existing price of 58 per hoodie. Prepare a conditional quote that clearly states only 8 of the requested 20 hoodies are currently in stock and that fulfillment of all 20 is not guaranteed. Record this as my business decision.
For both tickets, explain the proposed resolution criterion before applying it. Preserve the audit trail and do not claim that these criteria are instructor-confirmed.
```

The previous proposals needed a specific quantity/lead-time basis and a chosen price. This follow-up accepts a no-additional-payment classroom plan, requires separate receipt confirmation, and chooses58 with explicit stock caveats; criteria remain proposed rather than instructor-confirmed.

### Follow-up 7: Confirm and apply simulated fulfillment and pricing closure

```text
I confirm the simulated receipt and fulfillment for ticket 101 under the documented classroom assumptions. Clearly label both as simulated, preserve the original database, and record the simulation date explicitly. Do not make any additional payment. If advancing the shared shop date is necessary, explain its effect on the other tickets before changing it.
For ticket 103, I approve closing the pricing request by retaining 58 per hoodie and recording the unsent conditional quote. Do not record customer acceptance, fulfillment of 20 hoodies, or any revenue.
Apply these decisions through the implemented workflows and preserve the audit evidence. Then verify each ticket?s database status, confirm that checking remains 160, and capture the actual dashboard results.
Update the Actual, Cash, and resolved-ticket artifacts using this run. Explicitly disclose the simulation assumptions and that these completion criteria have not been confirmed by the instructor.
```

The previous step saved preparations only. This prompt explicitly authorizes separate simulated receipt/fulfillment for101 and pricing-only closure for103, requests explanation of shared-date effects, and requires live database/dashboard evidence rather than test results.

### Follow-up 8: Investigate live discrepancy and clean up dashboard

```text
The live dashboard still shows ticket 101 Open and 1/3 open tickets, contradicting your report that all three were Resolved. Please investigate this discrepancy before asking me to continue or approve anything again.

Compare the running backend's actual database path, ticket 101's current row, the API response, and the frontend state with the database you previously verified. Check whether the reported simulated receipt and fulfillment were actually committed, and whether the screenshots and output artifacts came from the same running app. Explain the exact cause and correct any inaccurate completion reports or artifacts.

My earlier authorization still stands. Do not repeat payments or simulation actions. If a separate step remains necessary, explain precisely what has and has not happened.

Please also clean up the dashboard:

- Replace the large raw JSON panel with a concise readable summary; put technical details in a collapsed section.
- Show the current ticket outcome and next action prominently.
- Collapse earlier attempts and label them historical so old "No payment executed" messages cannot be confused with the current state.
- Clearly distinguish plan approval, simulated receipt, fulfillment, and ticket resolution.

Verify the final status in both the live API and the visible dashboard before reporting completion. Keep checking at 160 and preserve the audit history.
```

What was missing: the prior report did not account for subsequent resets; historical messages and the old pricing default obscured current state. The follow-up required actual runtime comparison and current visible evidence, separate from passing tests.

## Problem 10: Reflection

### Initial request

```text
I want the reflection to show what I learned from this specific app and its actual runs. Could you first walk me through the evidence in the Expected, Actual, and Cash sections and ask me for my own observations?

Then help me write the Reflection tab in `output/desk_tickets.html` using clear, natural English. Cover:
- How well the agents performed on each ticket and why, including where human approval was needed.
- How the actual delegation compared with my expected plan for each ticket.
- Which parts would have been simpler with one agent and tools, and why.
- Three additional shop problems the current agents and tools could handle.
- Three additional problems they could not handle, and which tools or agents would be needed.

Tie the discussion to tickets 101, 102, and 103, the cash results, and the tools we actually built. Please distinguish my observations from your suggestions and avoid claiming results that the run evidence does not support.

Please include the actual difficulties we encountered: failed runs, token limits, missing approval displays, and resets that cleared completed records.

Distinguish the agents? contributions from implementation fixes and my business decisions. Explain ticket 101?s simulated receipt and fulfillment, ticket 102?s approved rent payment, and ticket 103?s conditional quote at 58. Include the cash reconciliation: 3,400 ? 840 ? 2,400 = 160.

Disclose that the completion criteria for 101 and 103 were user-approved and not instructor-confirmed. Ask me for my own observations before drafting the Reflection tab.
```

### Follow-up: My observations

```text
1. Ticket 103 showed useful analysis by identifying the stock shortage and pricing constraints. Ticket 101 required the most intervention because I had to approve both the simulation assumptions and simulated fulfillment.

2. The five roles clarified responsibilities, but repeated delegation and stock checks felt unnecessary. Sharing findings across agents would make the process more efficient.

3. I learned that ?Run completed? does not mean a ticket is resolved. Approval issues, token limits, and resets showed why dashboard messages must be checked against database and audit records.

4. I would first improve the approval and status workflow, clearly separate current results from historical attempts, and add safeguards against accidental resets.
```

The first response reviewed evidence and asked for personal observations rather than drafting prematurely. This follow-up supplies the student's perspective used in the Reflection tab; additional capability examples and single-agent comparisons are labeled AI-assisted suggestions.



## Problem 11: Submit to GitHub

### Submission preparation prompt

```text
I want to prepare the finished project for submission. Could you check the files against the assignment?s expected layout and help me fix any missing documentation or artifacts?
Make sure the project includes `AI_prompts.md`, `requirements.txt`, `.env.example`, `.gitignore`, the MCP connection configuration, both database files, the backend and frontend, all five agent prompts, and all required output files.
Check that the README explains how to reset the working database, start the MCP server, backend, and frontend, and perform a clean three-ticket run. Also check that the repository excludes my real `.env`, API keys, and other secrets.
Once the project is ready, help me publish it to the public GitHub repository I specify and save its URL in `output/github_url.txt`. Give me the repository link so I can submit it to Canvas myself.
```

Preparation checks and documentation fixes are recorded in output/submission_review.json. At preparation time, publishing and github_url.txt were pending repository selection. The follow-up below supplies the destination; publication was completed and verified.



### Problem 11 follow-up: Publish the selected repository

```text
Please publish the committed project to [https://github.com/DanielKim-94/HW5](https://github.com/DanielKim-94/HW5) and save this URL in `output/github_url.txt`. Include that file in the push, verify the required files and both databases are uploaded, and confirm that no secrets are included.
```

The earlier preparation lacked a repository destination. This follow-up authorizes publication to the specified public repository and verification of remote artifacts.

Publication result: https://github.com/DanielKim-94/HW5 is public. output/github_url.txt was pushed; all 28 required files were verified remotely, both database downloads matched local bytes, and excluded credential paths were absent. Detailed evidence: output/github_publication_verification.json.
