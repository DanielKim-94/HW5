# Campus Customs dashboard

React, Vite, and TypeScript workspace for the existing Campus Customs API.

From HW5/frontend:

```powershell
npm install
npm run dev
```

Open http://localhost:5174. The backend must run on http://localhost:8000. Port 5174 avoids the existing Lecture 12 app on 5173. Vite uses a strict port so the documented CORS origin stays predictable.

**Reset working database** is in the top-right header. Unlock human actions,
open the reset dialog, and select **Confirm database reset** to restore the
working copy from the original. This removes working-copy changes and preserves
audit history. It is disabled during an active run.

For the real clean run, capture each resolved ticket from frontend/:

```powershell
node scripts/capture-ticket.mjs 101
node scripts/capture-ticket.mjs 102
node scripts/capture-ticket.mjs 103
```

The helper checks both the actual API and dashboard resolved status, captures
the real page, writes a hash/evidence sidecar, and records the screenshot in
output/clean_run_manifest.json. It refuses open tickets and never mocks data.
From HW5, refresh recorded run evidence and the static Actual/Cash page:

```powershell
.\.venv\Scripts\python.exe output/manage_clean_run.py status
.\.venv\Scripts\python.exe output/update_actuals.py
```

Do not reset between tickets in a batch. Agent runs now stop automatically when
a pending approval is created; review and approve or decline in the dashboard,
then continue the same ticket in a new run. No helper auto-approves spending.

Optional VITE_API_URL changes the API URL; it must contain no secrets. Unlock human actions using your name and the token in ../backend/.human_api_token. The token is held only in browser memory. Reviewing and confirming an approval can spend real working-database cash; running a ticket invokes the configured agent team.

```powershell
npm run build
npm test
```

Browser tests require installed Google Chrome and both development servers. Only the first test reads the live API; action tests use mock fixtures. Screenshots are written to ../output/. See ../output/design.md for layout and practical limits.

The started development process tree is recorded in ../output/frontend_process.json, with stdout/stderr logs beside it. To stop it, use taskkill /PID <recorded pid> /T /F so its child processes stop together. Do not stop the unrelated Lecture 12 server.
