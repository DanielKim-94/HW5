# Campus Customs dashboard design

The workspace opens at http://localhost:5174 and connects to the existing FastAPI backend at http://localhost:8000. Port 5173 belongs to the Lecture 12 app, so HW5 uses 5174 without stopping that app. Backend CORS permits both localhost and 127.0.0.1 on the configured Vite port.

## Layout

A Yale Blue sidebar keeps all three tickets visible, with their actual status and requester. Selecting a ticket reveals its details and an editable instruction for Boss. The three summary cards show open tickets, pending approvals, and the checking balance. The shop date comes from the backend's desk record.

The main column follows the work: ticket instructions, team activity, then five contribution cards. The activity feed exposes actual agent messages, delegation requests and returns, tool calls and results, and failures. Role filtering and expandable records let a manager scan quickly or inspect evidence. Contributions use recorded summaries and tool/handoff counts; they do not invoke another model.

Human review occupies a separate right column. Pending requests show the amount and relevant reference; the review dialog requires an explicit approval or decline. On narrow screens, the tickets become a compact top navigation and human review moves above the selected ticket so pending decisions remain noticeable.

## Visual choices

Yale Blue (#00356b) anchors navigation and primary actions. Pale backgrounds, white cards, restrained borders, and generous spacing separate work without heavy decoration. Agent cues combine color with initials and written labels: Boss navy, Inventory teal, Accounting ochre, Facilities violet, and Customer Service rose. Amber highlights pending human decisions. Icons are authored SVG, with no external image or font dependency.

Keyboard focus indicators, native modal focus handling, labeled inputs, reduced-motion support, and responsive layouts support practical use. Loading, disconnected, empty, and backend-refusal states each have specific text. A failed connection retains previously loaded values and reports them as stale instead of inventing a zero balance.

## Data and human decisions

The dashboard polls backend records and audit activity approximately every two seconds. A completed agent job never changes a ticket badge by itself: only the backend's ticket status determines resolution. After approval, the dashboard fetches the current checking balance and refreshes pending requests and tickets. Currency is unspecified in the source database, so amounts have no invented currency symbol.

Human actions require a name and the local bearer token from backend/.human_api_token. POST /session/verify checks the token without changing shop records. Credentials stay in React memory and are cleared by reloading; they are not placed in browser storage or agent instructions. Agents retain their existing restriction against approving payments. The backend and MCP enforce cash, duplicate-payment, and stale-request safeguards; UI checks are supplementary.

## Verification and limits

The top-right header now includes **Reset working database**. A dialog describes the working-copy records that will be removed, requires unlocked human access, and offers a separate **Confirm database reset** action. It posts the exact backend confirmation to POST /reset, then clears cached job state and refreshes actual tickets, approvals, balance, and preserved audit history. Reset is disabled during a run or lost connection; backend refusal remains visible. The original database is never changed. Seven browser tests now pass, including confirmed reset and reset refusal using mocked HTTP responses; the real database was not reset.

The production TypeScript/Vite build passed. Five Playwright tests passed: live read-only ticket/cash display and responsive layout; recorded run activity and contributions without false resolution; human review and refreshed cash; backend refusal without cash changes; and network failure with an unavailable balance. Interaction tests use mocked HTTP fixtures and do not run real agents or spend shop cash. Desktop and mobile screenshots are saved alongside this document.

Activity is polling rather than a streaming connection. The browser retains at most 1,000 events per ticket; the full audit remains on disk. Backend jobs are in memory and can be interrupted by reload; this is displayed as an interruption when a job disappears. No live model run, real payment, purchase, or database reset was performed for this dashboard verification.


Runtime verification: get_runtime_identity reads SQLite database_list and exposes actual path/PID through GET /health. Human-only POST /recovery/committed-resolution calls recover_committed_resolution with human capability and expected reset sequence. It corroborates preserved completion against audit and checks cash, paid obligations, stock and pricing before restoring erased records. No payment or stock operation is replayed; agents cannot approve recovery. Result 1491 restored authorized completion after resets 1352/1454/1472. Current outcome reads actual ticket rows; historical attempts and technical JSON are collapsed; four completion stages are distinct. See output/discrepancy_investigation.md for current actual evidence and classroom limitations.
