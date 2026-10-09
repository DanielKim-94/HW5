// Capture the real dashboard only after both API and UI confirm resolution.
import { chromium } from '@playwright/test';
import { readFile, writeFile, mkdir } from 'node:fs/promises';
import { resolve } from 'node:path';
import { createHash } from 'node:crypto';

const ticketId = Number(process.argv[2]);
if (![101, 102, 103].includes(ticketId)) throw new Error('Supply ticket 101, 102, or 103');
const root = resolve(import.meta.dirname, '../..');
const manifestPath = resolve(root, process.argv[3] || 'output/clean_run_manifest.json');
const manifest = JSON.parse(await readFile(manifestPath, 'utf8'));
const visibleBrowser = process.argv.includes('--visible');
const browser = await chromium.launch({ channel: 'chrome', headless: !visibleBrowser });
try {
  const page = await browser.newPage({ viewport: { width: 1440, height: 1100 } });
  const response = await page.request.get('http://localhost:8000/tickets');
  if (!response.ok()) throw new Error('Backend ticket verification failed');
  const records = await response.json();
  const ticket = records.tickets.find(item => item.id === ticketId);
  if (ticket?.status !== 'resolved') throw new Error(`Ticket ${ticketId} is ${ticket?.status}; no resolution screenshot captured`);
  await page.goto('http://localhost:5174');
  await page.getByRole('button', { name: new RegExp(`#${ticketId}.*${ticket.subject}`) }).click();
  await page.getByTestId('ticket-status').filter({ hasText: 'resolved' }).waitFor();
  await page.locator('details.ticket-notes').evaluate(element => { element.open = true; });
  const cash = await (await page.request.get('http://localhost:8000/cash')).json();
  await page.getByTestId('checking-balance').filter({ hasText: Number(cash.account.balance).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 }) }).waitFor();
  if ([101,103].includes(ticketId)) await page.getByRole('region', {name:'Current completion steps'}).getByText(/None required for this ticket. Keep the completion evidence./).waitFor();
  await page.locator('.activity-feed').evaluate(element => { element.scrollTop = element.scrollHeight; });
  await page.locator('.metrics .metric-value').first().filter({hasText:/0\s*\/\s*3/}).waitFor();
  const liveHealth = await (await page.request.get('http://localhost:8000/health')).json();
  const visibleOutcome = await page.getByTestId('current-ticket-outcome').innerText();
  const finalRecords = await (await page.request.get('http://localhost:8000/tickets')).json();
  if (finalRecords.tickets.find(item => item.id === ticketId)?.status !== 'resolved') throw new Error('Ticket status changed before screenshot');
  await mkdir(resolve(root, 'output/screenshots'), { recursive: true });
  const relative = `output/screenshots/${manifest.batch_id}_ticket_${ticketId}_resolved.png`;
  const screenshot = await page.screenshot({ path: resolve(root, relative), fullPage: true });
  const evidence = { path: relative, ticket_id: ticketId, captured_utc: new Date().toISOString(),
    ticket, cash, completion_batch: manifest.batch_id, instructor_confirmed: manifest.instructor_confirmed ?? false, simulation_disclosure: ticketId === 101 ? manifest.simulation_assumptions : null, screenshot_sha256: createHash('sha256').update(screenshot).digest('hex'),
    dashboard_url: page.url(), visible_browser:visibleBrowser, visible_current_outcome:visibleOutcome, running_backend_identity:liveHealth.runtime, database_reset_sequence:manifest.after_reset_sequence, api_confirmed_resolved: true, mocked: false };
  await writeFile(resolve(root, relative + '.json'), JSON.stringify(evidence, null, 2) + '\n');
  manifest.resolved_screenshots[String(ticketId)] = evidence;
  await writeFile(manifestPath, JSON.stringify(manifest, null, 2) + '\n');
  console.log(relative);
} finally { await browser.close(); }
