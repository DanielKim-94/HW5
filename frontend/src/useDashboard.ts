import { useCallback, useEffect, useRef, useState } from 'react';
import { api } from './api';
import type { Activity, Approval, AuditEntry, Cash, Job, Snapshot, Ticket } from './types';

const initial: Snapshot = { tickets: [], businessDate: null, cash: null, payments: [], purchases: [], activeRunId: null, jobs: {} };

export function useDashboard(ticketId: number) {
  const [snapshot, setSnapshot] = useState<Snapshot>(initial);
  const [entries, setEntries] = useState<AuditEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [updatedAt, setUpdatedAt] = useState<Date | null>(null);
  const [revision, setRevision] = useState(0);
  const cache = useRef(new Map<number, { entries: AuditEntry[]; cursor: number }>());
  const jobs = useRef<Record<number, Job>>({});
  const refresh = useCallback(() => setRevision(value => value + 1), []);
  const rememberRun = useCallback((job: Job) => {
    jobs.current = { ...jobs.current, [job.ticket_id]: job };
    setSnapshot(value => ({ ...value, activeRunId: job.run_id, jobs: jobs.current }));
    refresh();
  }, [refresh]);
  const confirmCash = useCallback((cash: Cash) => setSnapshot(value => ({ ...value, cash })), []);
  const afterReset = useCallback(() => {
    jobs.current = {};
    cache.current.clear();
    setEntries([]);
    setSnapshot(value => ({ ...value, activeRunId: null, jobs: {}, payments: [], purchases: [] }));
    refresh();
  }, [refresh]);

  useEffect(() => {
    const controller = new AbortController();
    let timer: ReturnType<typeof setTimeout>;
    setEntries(cache.current.get(ticketId)?.entries || []);
    setLoading(!cache.current.has(ticketId));
    async function poll() {
      try {
        const cursor = cache.current.get(ticketId)?.cursor || 0;
        const [tickets, cash, approvals, health, activity, recent] = await Promise.all([
          api<{ tickets: Ticket[]; business_date: string }>('/tickets', { signal: controller.signal }),
          api<Cash>('/cash', { signal: controller.signal }),
          api<{ payments: Approval[]; purchases: Approval[] }>('/approvals', { signal: controller.signal }),
          api<{ active_run_id: string | null; runtime?:{working_database_path:string;mcp_pid:number} }>('/health', { signal: controller.signal }),
          api<Activity>(`/activity?ticket_id=${ticketId}&limit=200&after_sequence=${cursor}`, { signal: controller.signal }),
          api<{runs:Job[];last_reset_sequence?:number}>('/runs', {signal:controller.signal}),
        ]);
        if (controller.signal.aborted) return;
        jobs.current = {};
        for (const recovered of recent.runs || []) if (!jobs.current[recovered.ticket_id]) jobs.current[recovered.ticket_id] = recovered;
        const ids = new Set(Object.values(jobs.current).filter(job => ['queued', 'running'].includes(job.status)).map(job => job.run_id));
        if (health.active_run_id) ids.add(health.active_run_id);
        const states = await Promise.all([...ids].map(async id => {
          try { return await api<Job>(`/runs/${encodeURIComponent(id)}`, { signal: controller.signal }); }
          catch (err) {
            if (err instanceof Error && 'status' in err && err.status === 404) {
              const prior = Object.values(jobs.current).find(job => job.run_id === id);
              return prior ? { ...prior, status: 'interrupted', error: { type: 'Restart', message: 'Run status was lost after a backend restart. Review the activity before starting again.' } } : null;
            }
            throw err;
          }
        }));
        if (controller.signal.aborted) return;
        for (const job of states) if (job) jobs.current[job.ticket_id] = job;
        const merged = new Map((cache.current.get(ticketId)?.entries || []).map(entry => [entry.sequence, entry]));
        for (const entry of activity.entries) merged.set(entry.sequence, entry);
        const ordered = [...merged.values()].sort((a, b) => a.sequence - b.sequence).slice(-1000);
        cache.current.set(ticketId, { entries: ordered, cursor: activity.next_after_sequence });
        setEntries(ordered);
        setSnapshot({ tickets: tickets.tickets, businessDate: tickets.business_date, cash,
          payments: approvals.payments, purchases: approvals.purchases, activeRunId: health.active_run_id, jobs: { ...jobs.current }, runtime:health.runtime,lastResetSequence:recent.last_reset_sequence });
        setError('');
        setUpdatedAt(new Date());
        setLoading(false);
      } catch (err) {
        if (controller.signal.aborted) return;
        setError(err instanceof Error ? err.message : 'Unable to load the shop desk.');
        setLoading(false);
      } finally {
        if (!controller.signal.aborted) timer = setTimeout(poll, 2000);
      }
    }
    void poll();
    return () => { controller.abort(); clearTimeout(timer); };
  }, [ticketId, revision]);

  return { snapshot, entries, loading, error, updatedAt, refresh, rememberRun, confirmCash, afterReset };
}
