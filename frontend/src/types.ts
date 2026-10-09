export const roles = ['Boss', 'Inventory', 'Accounting', 'Facilities', 'Customer Service'] as const;
export type Role = typeof roles[number];
export interface Ticket {
  id: number; type: string; requester: string; subject: string; status: string;
  sku: string | null; size: string | null; qty: number | null; notes: string | null;
  lease_id: number | null; invoice_id: number | null; created_at: string;
}
export interface Cash { account: { name: string; balance: number; date: string }; business_date: string; currency: string | null }
export interface Approval {
  id: string; ticket_id: number; status: string; amount: string; account: string;
  kind?: string; ref_id?: number; due_date?: string; reason?: string;
  vendor_id?: number; sku?: string; size?: string; qty?: number; unit_cost?: string;
  supplier_evidence?: string; lead_days_snapshot?: number; requested_on: string;
}
export type ReviewRequest = Approval & { request_type: 'payment' | 'purchase' };
export interface Report {
  ticket_id: number; agent: Role; summary: string; status: string;
  evidence?: string[]; uncertainties?: string[]; approval_request_ids?: string[]; next_actions?: string[];
}
export interface Job {
  run_id: string; ticket_id: number; agent: Role; status: string;
  result?: Report; error?: { type: string; message: string };
}
export interface AuditEntry {
  sequence: number; timestamp_utc: string; run_id: string; ticket: number | null; agent: string; event: string;
  delegation: { from: string; to: string; topic: string; task: string } | null;
  tool_calls: { tool: string; arguments: Record<string, unknown> }[];
  results: Record<string, unknown> | null; approval_requests: unknown[];
}
export interface Activity { entries: AuditEntry[]; latest_sequence: number; next_after_sequence: number }
export interface Snapshot {
  tickets: Ticket[]; businessDate: string | null; cash: Cash | null;
  payments: Approval[]; purchases: Approval[]; activeRunId: string | null;
  jobs: Record<number, Job>;
  runtime?: {working_database_path:string;mcp_pid:number};
  lastResetSequence?:number;
}
