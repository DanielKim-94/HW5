import type { AuditEntry, Report, Role } from './types';

export interface DisplayEvent { entry: AuditEntry; kind: 'message' | 'tool' | 'delegation' | 'system' | 'error'; title: string; text: string; details?: unknown }
const friendlyTools: Record<string, string> = {
  get_ticket_context: 'Read ticket records', get_customer_order_context: 'Check tee order context',
  get_bulk_pricing_context: 'Check hoodie stock and pricing', get_rent_payment_context: 'Check lease and rent',
  get_cash_obligations: 'Review cash and obligations', get_vendor_shipping_status: 'Check vendor shipping eligibility',
  request_payment_approval: 'Prepare payment for human review', request_purchase_approval: 'Prepare purchase for human review',
  save_message_draft: 'Save an unsent message', save_quote_draft: 'Save a quote draft',
  fulfill_customer_order: 'Fulfill from recorded stock', approve_and_execute_payment: 'Record human-approved payment',
  approve_and_execute_purchase: 'Record human-approved purchase', execute_approved_payment: 'Execute an approved payment',
};

export function displayEvent(entry: AuditEntry): DisplayEvent | null {
  const result = entry.results || {};
  const tool = entry.tool_calls?.[0]?.tool;
  if (entry.event === 'agent_completed') return { entry, kind: 'message', title: 'Contribution', text: String(result.summary || 'Agent returned its findings.'), details: result };
  if (entry.event === 'delegation_requested') return { entry, kind: 'delegation', title: `Asked ${entry.delegation?.to || 'another agent'} for help`, text: entry.delegation?.task || '', details: entry.delegation };
  if (entry.event === 'delegation_returned') return { entry, kind: 'delegation', title: `${entry.delegation?.to || 'Specialist'} returned findings`, text: String(result.summary || ''), details: result };
  if (entry.event === 'tool_requested' || entry.event === 'dashboard_tool_requested') return { entry, kind: 'tool', title: friendlyTools[tool] || tool || 'Tool requested', text: 'Requested', details: entry.tool_calls };
  if (entry.event === 'tool_result' || entry.event === 'dashboard_tool_result') return { entry, kind: 'tool', title: friendlyTools[tool] || tool || 'Tool result', text: entry.approval_requests?.length ? 'Pending human approval · no payment executed' : 'Result recorded', details: result };
  if (entry.event === 'agent_started') return { entry, kind: 'system', title: 'Started work', text: String(result.task || '') };
  if (entry.event === 'loop_step_completed') {
    const next = result.next as { model_response?: { parts?: { part_kind: string; content?: string }[] } } | undefined;
    const text = next?.model_response?.parts?.filter(part => part.part_kind === 'text').map(part => part.content || '').join('\n');
    return text ? { entry, kind: 'message', title: 'Message', text } : null;
  }
  if (entry.event.includes('failed') || entry.event === 'agent_stopped' || entry.event === 'run_timeout' || entry.event === 'dashboard_run_interrupted') {
    return { entry, kind: 'error', title: entry.event.replaceAll('_', ' '), text: String(result.message || result.error || result.error_type || 'The run stopped. Review the recorded details.'), details: result };
  }
  if (entry.event === 'dashboard_run_queued') return { entry, kind: 'system', title: 'Run queued', text: String(result.task || '') };
  return null;
}

export function contribution(entries: AuditEntry[], role: Role) {
  const own = entries.filter(entry => entry.agent === role);
  const reports = own.filter(entry => entry.event === 'agent_completed');
  const lastReport = reports.at(-1)?.results as unknown as Report | undefined;
  return { report: lastReport, actions: own.filter(entry => entry.event === 'tool_result').length,
    delegations: own.filter(entry => entry.event === 'delegation_requested').length,
    started: own.some(entry => entry.event === 'agent_started'),
    active: own.at(-1)?.event !== 'agent_completed' && own.some(entry => entry.event === 'agent_started') };
}
