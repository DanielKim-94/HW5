import { useEffect, useMemo, useRef, useState } from 'react';
import type { CSSProperties, FormEvent, ReactNode } from 'react';
import { ResolutionReview } from './ResolutionReview';
import { api, ApiError } from './api';
import { contribution, displayEvent } from './activity';
import { roles } from './types';
import type { Cash, Job, ReviewRequest, Ticket } from './types';
import { useDashboard } from './useDashboard';

const agentStyle: Record<string, { short: string; color: string; tint: string; job: string }> = {
  Boss: { short: 'B', color: '#00356b', tint: '#edf3fc', job: 'Coordination' },
  Inventory: { short: 'I', color: '#0c7768', tint: '#eaf7f2', job: 'Stock & supply' },
  Accounting: { short: 'A', color: '#94610a', tint: '#fff6df', job: 'Cash & pricing' },
  Facilities: { short: 'F', color: '#7053a2', tint: '#f4effc', job: 'Shop & lease' },
  'Customer Service': { short: 'CS', color: '#b34e69', tint: '#fceff3', job: 'Customer drafts' },
  Human: { short: 'H', color: '#566578', tint: '#eef1f5', job: 'Human decision' },
};
const numberFormat = new Intl.NumberFormat('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
const amount = (value: number | string | undefined) => value === undefined || !Number.isFinite(Number(value)) ? '—' : numberFormat.format(Number(value));
const shopDate = (value: string | null) => value ? new Date(`${value}T12:00:00`).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' }) : '—';
const clock = (value: string) => new Date(value).toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit', timeZone: 'America/New_York' });
const label = (value: string) => value.replaceAll('_', ' ');

function Icon({ name, size = 18 }: { name: 'bag' | 'play' | 'arrow' | 'check' | 'refresh' | 'lock' | 'close' | 'cash' | 'inbox' | 'activity'; size?: number }) {
  const paths: Record<string, ReactNode> = {
    bag: <><path d="M5 7h14v14H5z"/><path d="M9 7V5a3 3 0 0 1 6 0v2"/><path d="m9 14 2 2 4-5"/></>,
    play: <path d="m8 5 11 7-11 7z"/>, arrow: <><path d="M4 12h15m-6-6 6 6-6 6"/></>,
    check: <path d="m5 12 4 4L19 6"/>, refresh: <><path d="M20 7v5h-5"/><path d="M4 17a8 8 0 0 0 15-5M20 7A8 8 0 0 0 5 7"/></>,
    lock: <><rect x="5" y="10" width="14" height="11" rx="2"/><path d="M8 10V6a4 4 0 0 1 8 0v4m-4 4v3"/></>,
    close: <path d="m6 6 12 12M6 18 18 6"/>, cash: <><rect x="3" y="6" width="18" height="13" rx="2"/><path d="M3 10h18m-6 5h3"/></>,
    inbox: <><path d="m3 14 3-9h12l3 9v6H3z"/><path d="M3 14h5l2 3h4l2-3h5"/></>,
    activity: <path d="M3 12h4l3-7 4 14 3-7h4"/>,
  };
  return <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">{paths[name]}</svg>;
}

function Avatar({ role, small = false }: { role: string; small?: boolean }) {
  const style = agentStyle[role] || agentStyle.Human;
  return <span className={`avatar ${small ? 'small' : ''}`} style={{ '--agent': style.color, '--tint': style.tint } as CSSProperties}>{style.short}</span>;
}

function Modal({ title, children, onClose, busy = false }: { title: string; children: ReactNode; onClose: () => void; busy?: boolean }) {
  const ref = useRef<HTMLDialogElement>(null);
  useEffect(() => { const dialog = ref.current!; dialog.showModal(); return () => dialog.close(); }, []);
  return <dialog ref={ref} className="modal" aria-labelledby="modal-title" onCancel={event => { event.preventDefault(); if (!busy) onClose(); }}>
    <div className="modal-head"><h2 id="modal-title">{title}</h2><button type="button" className="icon-button" onClick={onClose} disabled={busy} aria-label="Close dialog"><Icon name="close"/></button></div>
    {children}
  </dialog>;
}

function defaultTask(ticket?: Ticket) {
  if (!ticket) return '';
  if (ticket.status === 'resolved') return `Ticket ${ticket.id} is resolved in the database. Review its recorded completion evidence; do not execute further payments or fulfillment.`;
  const plan = ticket.id === 101 ? 'Ask Inventory to verify stock and vendor shipping, and Accounting to prepare invoice 501 only if still unpaid. After payment, report the remaining genuine receipt/fulfillment evidence needed; do not prepare another payment.' : ticket.id === 102 ? 'Ask Facilities and Accounting to prepare recorded rent for human review even before its due date, unless already paid.' : 'Ask Accounting for recorded pricing and discount authority, with Inventory checking exact-size stock. Return missing supplier and discount authority as blockers; do not guess a policy, supplier or price.';
  return `Work only on ticket ${ticket.id}. ${plan} Reuse specialist findings instead of repeating reads or delegations. Return a concise evidence-based report. Keep all messages as unsent drafts.`;
}

export default function App() {
  const [selectedId, setSelectedId] = useState(101);
  const { snapshot, entries, loading, error, updatedAt, refresh, rememberRun, confirmCash, afterReset } = useDashboard(selectedId);
  const [preparation, setPreparation] = useState<Record<number, boolean>>({});
  const [tasks, setTasks] = useState<Record<number, string>>({});
  const [token, setToken] = useState('');
  const [humanName, setHumanName] = useState('');
  const [tokenInput, setTokenInput] = useState('');
  const [nameInput, setNameInput] = useState('');
  const [authOpen, setAuthOpen] = useState(false);
  const [resetOpen, setResetOpen] = useState(false);
  const [review, setReview] = useState<ReviewRequest | null>(null);
  const [busy, setBusy] = useState('');
  const [actionError, setActionError] = useState('');
  const [notice, setNotice] = useState('');
  const [agentFilter, setAgentFilter] = useState('All agents');
  const ticket = snapshot.tickets.find(item => item.id === selectedId);
  const job = snapshot.jobs[selectedId];
  const runActive = snapshot.activeRunId !== null || Object.values(snapshot.jobs).some(item => ['queued', 'running'].includes(item.status));
  const pending: ReviewRequest[] = [...snapshot.payments.map(item => ({ ...item, request_type: 'payment' as const })),
    ...snapshot.purchases.map(item => ({ ...item, request_type: 'purchase' as const }))].filter(item => item.status === 'pending');
  const selectedPending = pending.filter(item => item.ticket_id === selectedId);
  const sortedPending = [...pending].sort((a, b) => Number(b.ticket_id === selectedId) - Number(a.ticket_id === selectedId));
  const preparePayments = preparation[selectedId] ?? true;
  const linkedPaymentExecuted = snapshot.payments.some(item => item.ticket_id === selectedId && item.status === 'executed' && (ticket?.type === 'customer_order' ? item.kind === 'invoice' && item.ref_id === ticket.invoice_id : item.kind === 'rent' && item.ref_id === ticket?.lease_id));
  const decisionRecorded = [...snapshot.payments, ...snapshot.purchases].some(item => item.ticket_id === selectedId && ['executed','denied'].includes(item.status));

  const selectedTask = tasks[selectedId] ?? defaultTask(ticket);
  const events = useMemo(() => entries.map(displayEvent).filter(event => event !== null), [entries]);
  const visibleEvents = events.filter(event => agentFilter === 'All agents' || event.entry.agent === agentFilter);
  const summaryEntries = job ? entries.filter(entry => entry.run_id === job.run_id) : entries;

  function handleError(err: unknown) {
    const message = err instanceof Error ? err.message : 'The action could not be completed.';
    setActionError(message);
    if (err instanceof ApiError && err.status === 401) { setToken(''); setTokenInput(''); }
  }

  async function unlock(event: FormEvent) {
    event.preventDefault(); setBusy('unlock'); setActionError('');
    try {
      await api('/session/verify', { method: 'POST', token: tokenInput.trim() });
      setToken(tokenInput.trim()); setHumanName(nameInput.trim()); setTokenInput(''); setAuthOpen(false);
      setNotice('Human actions unlocked for this browser session.');
    } catch (err) { handleError(err); }
    finally { setBusy(''); }
  }

  async function runTicket(event: FormEvent) {
    event.preventDefault();
    if (!token) { setAuthOpen(true); return; }
    setBusy('run'); setActionError(''); setNotice('');
    try {
      const result = await api<Job>(`/tickets/${selectedId}/run`, { method: 'POST', token, body: { task: selectedTask, agent: 'Boss', prepare_payments: preparePayments } });
      rememberRun(result); setNotice(`Ticket ${selectedId} queued. Follow the team’s activity below.`);
    } catch (err) { handleError(err); }
    finally { setBusy(''); }
  }

  async function preparePayment() {
    if (!token) { setAuthOpen(true); return; }
    if (!ticket) return;
    setBusy('prepare'); setActionError('');
    try {
      await api(`/tickets/${selectedId}/payments/prepare`, {method:'POST', token, body:{kind: ticket.type === 'rent_notice' ? 'rent' : 'invoice', ref_id: ticket.type === 'rent_notice' ? ticket.lease_id : ticket.invoice_id, reason:'Human requested preparation for review only; no payment authorized.'}});
      setNotice('Request prepared for human review. No payment executed.'); refresh();
    } catch (err) { handleError(err); } finally { setBusy(''); }
  }

  async function decide(approve: boolean) {
    if (!review || !token) return;
    setBusy('decision'); setActionError(''); setNotice('');
    try {
      const request = review;
      await api(`/approvals/${encodeURIComponent(request.id)}/${approve ? 'approve' : 'deny'}`, {
        method: 'POST', token, body: { ticket_id: request.ticket_id, request_type: request.request_type, human_name: humanName, ...(approve ? { approve: true } : {}) },
      });
      setReview(null);
      setNotice(approve ? `${label(request.request_type)} recorded by the backend. Refreshing current records.` : 'Request declined. No payment was made.');
      refresh();
      try { confirmCash(await api<Cash>('/cash')); }
      catch { setNotice('Decision recorded. Balance refresh failed; the displayed balance may be stale. Retry refresh.'); }
    } catch (err) { handleError(err); refresh(); }
    finally { setBusy(''); }
  }

  async function resetDatabase() {
    if (!token) return;
    setBusy('reset'); setActionError(''); setNotice('');
    try {
      await api('/reset', { method: 'POST', token, body: { confirmation: 'RESET_WORKING_DATABASE' } });
      setResetOpen(false); setReview(null); afterReset();
      setNotice('Working database restored from the original. Audit history is preserved. Refreshing shop records.');
      try { confirmCash(await api<Cash>('/cash')); }
      catch { setNotice('Reset confirmed. Balance refresh failed; retry refresh before running tickets.'); }
    } catch (err) { handleError(err); refresh(); }
    finally { setBusy(''); }
  }

  return <div className="workspace">
    <aside className="sidebar">
      <a className="brand" href="/" aria-label="Campus Customs home"><span className="brand-mark"><Icon name="bag" size={27}/></span><span>Campus<br/><strong>Customs</strong></span></a>
      <div className="workspace-label">SHOP WORKSPACE</div>
      <div className="sidebar-section"><span>Ticket desk</span><span className="count">{snapshot.tickets.length || '—'}</span></div>
      <div className="ticket-list" aria-label="Select a ticket">
        {loading && !snapshot.tickets.length ? [1,2,3].map(item => <div className="ticket-skeleton" key={item}/>) : snapshot.tickets.map(item =>
          <button key={item.id} className={`ticket-button ${selectedId === item.id ? 'selected' : ''}`} onClick={() => { setSelectedId(item.id); setActionError(''); setNotice(''); setAgentFilter('All agents'); }} aria-pressed={selectedId === item.id}>
            <div className="ticket-button-top"><span>#{item.id}</span><span className={`status-dot ${item.status === 'resolved' ? 'resolved' : ''}`}/></div>
            <strong>{item.subject}</strong><span className="requester">{item.requester}</span>
            <span className={`sidebar-status ${item.status === 'resolved' ? 'resolved' : ''}`}>{label(item.status)}</span>
          </button>)}
      </div>
      <div className="sidebar-team"><div className="workspace-label">YOUR AGENT TEAM</div>{roles.map(role => <div className="team-row" key={role}><Avatar role={role} small/><span>{role}</span></div>)}</div>
      <div className="sidebar-bottom"><span className="connection-dot" data-connected={!error && updatedAt !== null}/><span>{error ? 'Connection needs attention' : updatedAt ? 'Connected to shop backend' : 'Connecting to shop backend'}</span></div>
    </aside>

    <main className="main">
      <header className="topbar"><div><p className="eyebrow">CAMPUS CUSTOMS / TICKET DESK</p><h1>A clear view of the shop.</h1><p className="muted">Your team investigates. You make the payment decisions.</p></div>
        <div className="header-actions"><span className="date-pill">Shop date <strong>{shopDate(snapshot.businessDate)}</strong></span>
          <button className="button outline" disabled={!!busy || runActive || !!error || !updatedAt} onClick={() => { setActionError(''); setResetOpen(true); }}><Icon name="refresh"/>Reset working database</button>
          <button className={`button ${token ? 'subtle' : 'outline'}`} onClick={() => { setActionError(''); if (token) { setToken(''); setHumanName(''); setNotice('Human actions locked.'); } else setAuthOpen(true); }}><Icon name="lock"/>{token ? `${humanName} · Lock` : 'Unlock human actions'}</button>
        </div>
      </header>

      {error && <div className="alert error" role="alert"><div><strong>Connection needs attention</strong><p>{error}{updatedAt ? ' Previously loaded records may be stale.' : ''}</p></div><button className="button outline" onClick={refresh}><Icon name="refresh"/>Retry</button></div>}
      {actionError && !authOpen && <div className="alert error" role="alert"><div><strong>Action not completed</strong><p>{actionError}</p></div><button className="icon-button" onClick={() => setActionError('')} aria-label="Dismiss error"><Icon name="close"/></button></div>}
      {notice && <div className="notice" role="status"><Icon name="check"/><span>{notice}</span></div>}

      <section className="metrics" aria-label="Shop overview">
        <article className="metric"><div className="metric-heading"><span>Open tickets</span><Icon name="inbox"/></div><strong className="metric-value">{snapshot.tickets.length ? snapshot.tickets.filter(item => item.status !== 'resolved').length : '—'}<span> / {snapshot.tickets.length || '—'}</span></strong><p>Current status from shop records</p></article>
        <article className={`metric ${pending.length ? 'attention' : ''}`}><div className="metric-heading"><span>Awaiting your approval</span><span className="mini-badge">HUMAN</span></div><strong className="metric-value">{updatedAt ? pending.length : '—'}</strong><p>{pending.length ? 'Prepared requests · nothing paid yet' : 'No pending payment or purchase requests'}</p></article>
        <article className="metric cash"><div className="metric-heading"><span>Checking balance</span><Icon name="cash"/></div><strong className="metric-value" data-testid="checking-balance">{amount(snapshot.cash?.account.balance)}</strong><p>As recorded {shopDate(snapshot.cash?.account.date || null)} · currency unspecified</p></article>
      </section>

      <div className="desk-layout">
        <div className="desk-center">
          <section className="card ticket-workspace" aria-busy={loading}>
            <div className="section-top"><span className="eyebrow">SELECTED TICKET · #{selectedId}</span>{ticket && <span className={`status-pill ${ticket.status === 'resolved' ? 'resolved' : 'open'}`} data-testid="ticket-status">{label(ticket.status)}</span>}</div>
            {ticket ? <><h2>{ticket.subject}</h2><p className="muted">{ticket.requester} <span className="separator">/</span> {label(ticket.type)}</p>
              <div className="ticket-facts">{ticket.sku && <span>{ticket.qty} × {ticket.sku} <b>Size {ticket.size}</b></span>}{ticket.lease_id && <span>Lease #{ticket.lease_id}</span>}{ticket.invoice_id && <span>Linked invoice #{ticket.invoice_id}</span>}</div>
              <details className="ticket-notes"><summary>Ticket notes ? chronological history</summary><p>{ticket.notes || 'No notes recorded.'}</p></details>
              {ticket.status !== 'resolved' && <form onSubmit={runTicket} className="run-form"><label htmlFor="task">What should Boss work on?</label><textarea id="task" rows={3} maxLength={4000} value={selectedTask} onChange={event => setTasks(value => ({ ...value, [selectedId]: event.target.value }))} disabled={runActive || busy === 'run'}/>
                <label className="small-text"><input type="checkbox" checked={preparePayments} onChange={event => setPreparation(value => ({...value, [selectedId]:event.target.checked}))}/> Prepare recorded payments for human review (never approve them)</label><div className="run-footer"><span className="muted small-text">One ticket at a time. Delegation stays relevant.</span><button type="submit" className="button primary" disabled={!!busy || runActive || !!error || !selectedTask.trim() || ticket?.status === 'resolved' || (preparePayments && selectedPending.length > 0)}>{busy === 'run' || runActive ? <span className="spinner"/> : <Icon name="play"/>}{ticket?.status === 'resolved' ? 'Resolved' : runActive ? 'Team working…' : selectedPending.length && preparePayments ? 'Review approval first' : decisionRecorded && ticket?.status === 'open' ? 'Continue ticket' : 'Run ticket'}</button></div>
              </form>}</> : <div className="empty"><span className={loading ? 'spinner' : ''}/><p>{loading ? 'Loading ticket records…' : 'Ticket records are unavailable. Retry the connection.'}</p></div>}
            {ticket && <div className="run-status" role="status" data-testid="current-ticket-outcome"><strong>Current outcome: {ticket.status === 'resolved' ? 'Resolved: database confirmed' : 'Open: database confirmed'}</strong><span>{ticket.status === 'resolved' ? selectedId===101 ? 'Simulated receipt and fulfillment are recorded. No physical delivery claimed.' : selectedId===103 ? 'Pricing request closed; the quote is unsent and conditional. No hoodie fulfillment or revenue.' : 'Approved rent payment recorded.' : selectedId===101&&linkedPaymentExecuted ? 'Invoice paid. Plan approval alone does not record simulated receipt or fulfillment.' : job?.result?.summary || 'Review the current completion steps and recorded facts.'}</span><p><strong>Next action:</strong> {ticket.status === 'resolved' ? 'None. Keep the evidence; do not repeat payments or completion actions.' : selectedId===101&&linkedPaymentExecuted ? 'Verify the separately authorized receipt and fulfillment records; no new payment is needed.' : selectedPending.length ? 'Review the existing request.' : 'Review the current business proposal.'}</p></div>}
            {job && ['queued','running','failed','interrupted'].includes(job.status) && <div className="run-status"><strong>Agent job: {label(job.status)}</strong><span>{job.error?.message || 'Activity is being recorded.'}</span></div>}
            {runActive && !job && <p className="small-text muted">Another ticket is being worked on. You can review this ticket while the team finishes.</p>}
          </section>

          <details className="card activity-card"><summary>Earlier attempts and audit history - historical</summary>
            <div className="section-top"><div><h2 className="section-heading"><Icon name="activity"/>Team activity</h2><p className="muted small-text">Recorded history (including earlier attempts) for ticket #{selectedId}</p></div><div className="live-label"><span className={`connection-dot ${runActive ? 'pulse' : ''}`} data-connected={!error && updatedAt !== null}/>{error ? 'Updates paused' : runActive ? 'Updating live' : 'Auto-refresh'}</div></div>
            <div className="activity-toolbar"><label className="sr-only" htmlFor="agent-filter">Filter activity by agent</label><select id="agent-filter" value={agentFilter} onChange={event => setAgentFilter(event.target.value)}><option>All agents</option>{roles.map(role => <option key={role}>{role}</option>)}<option>Human</option></select><button className="icon-button" onClick={refresh} aria-label="Refresh shop records"><Icon name="refresh"/></button></div>
            <div className="activity-feed" aria-label="Agent activity" aria-busy={loading}>
              {!visibleEvents.length ? <div className="empty"><span className="empty-icon"><Icon name="activity" size={27}/></span><strong>{loading ? 'Loading activity…' : 'The team’s work will appear here'}</strong><p>{loading ? 'Reading recorded events.' : 'Run this ticket to see actual messages, tool results, and specialist handoffs.'}</p></div> : visibleEvents.map(event =>
                <article key={event.entry.sequence} className={`activity-event ${event.kind}`}><Avatar role={event.entry.agent}/><div className="event-body"><div className="event-meta"><strong>{event.entry.agent}</strong><span className="event-kind">{event.kind}</span><time dateTime={event.entry.timestamp_utc}>{clock(event.entry.timestamp_utc)}</time></div><h3>{event.title}</h3><p>{event.text}</p>{event.details != null && <details><summary>Recorded details</summary><pre>{JSON.stringify(event.details, null, 2)}</pre></details>}</div></article>)}
            </div>
          </details>

          <details className="contributions" aria-label="Each agent’s contribution"><summary>Earlier agent contributions - historical</summary><div className="section-top"><h2 className="section-heading">Who contributed what</h2><span className="muted small-text">{job ? 'Earlier agent run - historical findings' : 'Selected ticket history'}</span></div>
            <div className="agent-grid">{roles.map(role => { const own = contribution(summaryEntries, role); return <article key={role} className="agent-card" style={{ '--agent': agentStyle[role].color } as CSSProperties}><div className="agent-heading"><Avatar role={role}/><div><h3>{role}</h3><p>{agentStyle[role].job}</p></div></div><p className="agent-summary">{own.report?.summary || (own.started ? 'Work started. Findings have not yet been returned.' : 'No contribution recorded yet.')}</p><div className="agent-counts"><span>{own.actions} tool result{own.actions === 1 ? '' : 's'}</span><span>{own.delegations} handoff{own.delegations === 1 ? '' : 's'}</span></div>{own.report?.next_actions?.length ? <details><summary>Next actions</summary><ul>{own.report.next_actions.map((text, index) => <li key={index}>{text}</li>)}</ul></details> : null}</article>; })}</div>
          </details>
        </div>

        <aside className="review-column">
          {(selectedId===103 || selectedId===101 && linkedPaymentExecuted) && <ResolutionReview ticketId={selectedId} token={token} humanName={humanName} disabled={runActive || !!busy || !!error || ticket?.status === 'resolved'} onChanged={refresh}/> }
          <section className={`card approval-card ${pending.length ? 'has-pending' : ''}`}><div className="section-top"><h2 className="section-heading">Human review</h2><span className="approval-count">{pending.length}</span></div><p className="muted small-text">Prepared requests need your decision.</p>
            {sortedPending.length ? <div className="approval-list">{sortedPending.map(item => <article className="request-card" key={item.id}><div className="request-top"><span className="request-kind">{item.request_type === 'payment' ? `${label(item.kind || 'Payment')}` : 'Purchase'}</span><button className="ticket-link" onClick={() => setSelectedId(item.ticket_id)}>#{item.ticket_id}</button></div><strong className="request-amount">{amount(item.amount)}</strong><p>{item.request_type === 'purchase' ? `${item.qty} × ${item.sku}, ${item.size}` : item.kind === 'rent' ? `Lease #${item.ref_id}` : `Invoice #${item.ref_id}`}</p><span className="pending-tag">Pending approval</span><button className="button review-button" onClick={() => { setReview(item); setActionError(''); }} disabled={!!busy}>Review request <Icon name="arrow"/></button></article>)}</div> : <div className="approval-empty"><span className="empty-icon"><Icon name="check" size={24}/></span><strong>{updatedAt ? ticket?.status === 'resolved' ? 'Resolved: database confirmed' : job?.result?.status === 'blocked' ? 'Business decision needed' : linkedPaymentExecuted ? 'Payment completed' : 'No pending spending approvals' : 'Loading approvals…'}</strong><p>{ticket?.status === 'resolved' ? selectedId === 101 ? 'Classroom simulated receipt and fulfillment recorded. No physical delivery claimed.' : selectedId === 103 ? 'Pricing request closed at 58 with an unsent conditional quote. No customer acceptance or hoodie fulfillment claimed.' : 'Human-approved rent payment recorded.' : job?.result?.status === 'blocked' ? job.result.summary : linkedPaymentExecuted && ticket?.status === 'open' ? 'The invoice is paid. Stock receipt and fulfillment remain unverified; another payment will not resolve the ticket.' : 'No payment or purchase request is pending. This does not mean the ticket is resolved.'}</p>{ticket?.status !== 'resolved' && job?.result?.status === 'blocked' && <ul>{job.result.next_actions?.map((action,index) => <li key={index}>{action}</li>)}</ul>}</div>}
            {ticket?.status === 'open' && (ticket.invoice_id || ticket.lease_id) && !selectedPending.length && !linkedPaymentExecuted && <button className="button outline full" disabled={!!busy || runActive || !!error} onClick={() => void preparePayment()}>Prepare payment request</button>}{linkedPaymentExecuted && ticket?.status === 'open' && <p className="small-text muted">Invoice payment is recorded. This ticket still needs genuine stock receipt and fulfillment evidence. Use Continue ticket to review the remaining blocker.</p>}<div className="review-footnote"><Icon name="lock" size={15}/><span>Approval is always a human action.</span></div>
          </section>
          <section className="card guide-card"><span className="eyebrow">FOR THIS TICKET</span><h3>{selectedPending.length ? `${selectedPending.length} decision${selectedPending.length === 1 ? '' : 's'} waiting` : 'Keep the next step clear'}</h3><p>Boss brings in the relevant specialists. Review their evidence, then decide on any prepared spending.</p><div className="guide-rule"><Icon name="check" size={16}/><span>Resolved status comes from shop records.</span></div><div className="guide-rule"><Icon name="inbox" size={16}/><span>Customer and vendor messages stay drafts.</span></div></section>
        </aside>
      </div>
      <details className="small-text muted"><summary>Live connection details</summary><p>Backend: http://localhost:8000</p><p>Working database: {snapshot.runtime?.working_database_path || 'Identity not yet reported'}</p><p>Last recorded reset sequence: {snapshot.lastResetSequence ?? 'unknown'}</p></details><footer className="page-footer"><span>Campus Customs · Shop desk</span><span>{updatedAt ? `Last checked ${updatedAt.toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit', second: '2-digit', timeZone: 'America/New_York' })} ET` : 'Waiting for backend records'}</span></footer>
    </main>

    {authOpen && <Modal title="Unlock human actions" onClose={() => { setAuthOpen(false); setTokenInput(''); }} busy={busy === 'unlock'}><p className="muted">Enter your name and the local human access token to run the team or approve spending.</p><form onSubmit={unlock} className="auth-form"><label htmlFor="human-name">Your name</label><input id="human-name" value={nameInput} onChange={event => setNameInput(event.target.value)} required maxLength={200} autoComplete="name" autoFocus/><label htmlFor="human-token">Human access token</label><input id="human-token" type="password" value={tokenInput} onChange={event => setTokenInput(event.target.value)} required minLength={32} autoComplete="off" spellCheck={false}/><p className="small-text muted">Use the token in <code>backend/.human_api_token</code>. It stays in memory for this browser session and is never included in agent prompts.</p>{actionError && <div className="inline-error" role="alert">{actionError}</div>}<button className="button primary full" disabled={!!busy || !nameInput.trim() || tokenInput.trim().length < 32}>{busy === 'unlock' ? <span className="spinner"/> : <Icon name="lock"/>}Unlock actions</button></form></Modal>}

    {review && <Modal title={`Review ${review.request_type}`} onClose={() => setReview(null)} busy={busy === 'decision'}><div className="approval-preview"><span className="pending-tag">Pending · Ticket #{review.ticket_id}</span><strong>{amount(review.amount)}</strong><span>From {review.account}</span></div><dl className="review-details"><div><dt>Request</dt><dd>{review.request_type === 'purchase' ? `${review.qty} × ${review.sku}, size ${review.size}` : `${label(review.kind || 'payment')} · reference #${review.ref_id}`}</dd></div>{review.due_date && <div><dt>Due date</dt><dd>{shopDate(review.due_date)}</dd></div>}{review.vendor_id && <div><dt>Vendor</dt><dd>#{review.vendor_id}</dd></div>}{review.unit_cost && <div><dt>Recorded unit cost</dt><dd>{amount(review.unit_cost)}</dd></div>}<div><dt>Checking balance</dt><dd>{amount(snapshot.cash?.account.balance)}</dd></div>{review.reason && <div><dt>Reason</dt><dd>{review.reason}</dd></div>}{review.supplier_evidence && <div><dt>Supplier evidence</dt><dd>{review.supplier_evidence}</dd></div>}{token && <div><dt>Approving as</dt><dd>{humanName}</dd></div>}</dl><p className="small-text muted">The backend rechecks the request and available cash before spending. {review.request_type === 'purchase' ? 'It also checks vendor invoices. A purchase records an order, not received stock.' : 'A prepared request has not yet been paid.'}</p>{runActive && <div className="inline-error">Wait for the active team run to finish before deciding.</div>}{snapshot.cash && Number(review.amount) > snapshot.cash.account.balance && <div className="inline-error">Insufficient checking cash for this request.</div>}{actionError && <div className="inline-error" role="alert">{actionError}</div>}{token ? <div className="decision-buttons"><button className="button outline" onClick={() => void decide(false)} disabled={!!busy || runActive || !!error}>Decline</button><button className="button approval-primary" onClick={() => void decide(true)} disabled={!!busy || runActive || !!error || !snapshot.cash || Number(review.amount) > snapshot.cash.account.balance}>{busy === 'decision' ? <span className="spinner"/> : <Icon name="check"/>}Approve & pay {amount(review.amount)}</button></div> : <button className="button primary full" onClick={() => { setReview(null); setAuthOpen(true); }}>Unlock actions to approve</button>}</Modal>}
    {resetOpen && <Modal title="Restore working database" onClose={() => setResetOpen(false)} busy={busy === 'reset'}>
      <p className="muted">This replaces the working database with the original assignment data. Payments, purchases, approvals, drafts, stock changes, and ticket changes in the working copy will be removed. The original database stays unchanged and audit history is preserved.</p>
      <p className="small-text muted">This removes {pending.length} currently pending approval request(s). Completed receipts and resolutions are also cleared; prior screenshots become historical. After restoration, checking starts at 3,400.00 and all three tickets are open. Previous audit events remain historical evidence.</p>
      {actionError && <div className="inline-error" role="alert">{actionError}</div>}
      {token ? <div className="decision-buttons"><button className="button outline" disabled={!!busy} onClick={() => setResetOpen(false)}>Cancel</button><button className="button primary" disabled={!!busy || runActive || !!error} onClick={() => void resetDatabase()}>{busy === 'reset' && <span className="spinner"/>}Confirm database reset</button></div> : <button className="button primary full" onClick={() => { setResetOpen(false); setAuthOpen(true); }}>Unlock actions to reset</button>}
    </Modal>}
  </div>;
}
