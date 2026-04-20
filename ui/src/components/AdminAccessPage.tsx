import React, { useEffect, useMemo, useState } from 'react';
import { Copy, RefreshCcw } from 'lucide-react';

interface AdminUser {
  id: number;
  name: string;
  email: string;
  organization: string;
  use_case: string;
  role: 'user' | 'admin';
  status: 'pending' | 'granted' | 'denied';
  access_granted: boolean;
  created_at: string;
  updated_at: string;
  has_password?: boolean;
}

interface AdminRequestAudit {
  id: number;
  user_id: number;
  name: string;
  email: string;
  organization: string;
  use_case: string;
  status: 'pending' | 'granted' | 'denied';
  reviewed_by?: number | null;
  review_notes?: string;
  created_at: string;
  reviewed_at?: string | null;
}

interface AdminAccessResponse {
  ok: boolean;
  users: AdminUser[];
  requests: AdminRequestAudit[];
}

interface RowDraft {
  status: 'pending' | 'granted' | 'denied';
  access_granted: boolean;
  review_notes: string;
}

interface AccessEvent {
  id: number;
  occurred_at: string;
  ip_address: string;
  forwarded_for: string;
  real_ip: string;
  method: string;
  path: string;
  status_code: number;
  outcome: 'success' | 'client_error' | 'server_error';
  user_agent: string;
  referer: string;
  origin: string;
  query_string_present: boolean;
  user_id?: number | null;
  user_email: string;
  user_role: string;
  session_id?: number | null;
  is_authenticated: boolean;
}

interface AccessEventSummary {
  total: number;
  unique_ips: number;
  authenticated: number;
  anonymous: number;
  failed: number;
}

interface TopIpView {
  ip_address: string;
  hit_count: number;
  last_seen_at: string;
}

interface AdminAccessMonitoringResponse {
  ok: boolean;
  events: AccessEvent[];
  summary: AccessEventSummary;
  top_ips: TopIpView[];
  limit: number;
  offset: number;
  has_more: boolean;
}

interface MonitoringFilters {
  from: string;
  to: string;
  ip: string;
  userId: string;
  email: string;
  pathContains: string;
  statusCode: string;
  outcome: '' | 'success' | 'client_error' | 'server_error';
  authenticatedOnly: 'all' | 'yes' | 'no';
}

type AdminPanelView = 'user_management' | 'audit_history' | 'access_history';

const MONITORING_PAGE_SIZE = 25;

const EMPTY_MONITORING_SUMMARY: AccessEventSummary = {
  total: 0,
  unique_ips: 0,
  authenticated: 0,
  anonymous: 0,
  failed: 0,
};

function toDateInputValue(date: Date): string {
  const year = date.getFullYear();
  const month = `${date.getMonth() + 1}`.padStart(2, '0');
  const day = `${date.getDate()}`.padStart(2, '0');
  return `${year}-${month}-${day}`;
}

function getDefaultMonitoringFilters(): MonitoringFilters {
  const now = new Date();
  const from = new Date(now.getTime() - 7 * 24 * 60 * 60 * 1000);
  return {
    from: toDateInputValue(from),
    to: toDateInputValue(now),
    ip: '',
    userId: '',
    email: '',
    pathContains: '',
    statusCode: '',
    outcome: '',
    authenticatedOnly: 'all',
  };
}

function formatTimestamp(value?: string | null): string {
  if (!value) return '-';
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return value;
  return parsed.toLocaleString();
}

function outcomeBadgeClass(outcome: AccessEvent['outcome']): string {
  if (outcome === 'server_error') return 'bg-rose-100 text-rose-700';
  if (outcome === 'client_error') return 'bg-amber-100 text-amber-700';
  return 'bg-emerald-100 text-emerald-700';
}

function toIsoRangeStart(dateValue: string): string | null {
  if (!dateValue) return null;
  const parsed = new Date(`${dateValue}T00:00:00`);
  if (Number.isNaN(parsed.getTime())) return null;
  return parsed.toISOString();
}

function toIsoRangeEnd(dateValue: string): string | null {
  if (!dateValue) return null;
  const parsed = new Date(`${dateValue}T23:59:59`);
  if (Number.isNaN(parsed.getTime())) return null;
  return parsed.toISOString();
}

export const AdminAccessPage = ({ apiBase, authToken }: { apiBase: string; authToken: string }) => {
  const initialMonitoringFilters = useMemo(() => getDefaultMonitoringFilters(), []);
  const [users, setUsers] = useState<AdminUser[]>([]);
  const [requests, setRequests] = useState<AdminRequestAudit[]>([]);
  const [activeView, setActiveView] = useState<AdminPanelView>('user_management');
  const [drafts, setDrafts] = useState<Record<number, RowDraft>>({});
  const [setupLinks, setSetupLinks] = useState<Record<number, string>>({});
  const [monitoring, setMonitoring] = useState<AdminAccessMonitoringResponse>({
    ok: true,
    events: [],
    summary: EMPTY_MONITORING_SUMMARY,
    top_ips: [],
    limit: MONITORING_PAGE_SIZE,
    offset: 0,
    has_more: false,
  });
  const [monitoringDraftFilters, setMonitoringDraftFilters] = useState<MonitoringFilters>(initialMonitoringFilters);
  const [monitoringAppliedFilters, setMonitoringAppliedFilters] = useState<MonitoringFilters>(initialMonitoringFilters);
  const [loading, setLoading] = useState(false);
  const [monitoringLoading, setMonitoringLoading] = useState(false);
  const [error, setError] = useState('');
  const [message, setMessage] = useState('');

  const headers = useMemo(
    () => ({
      Authorization: `Bearer ${authToken}`,
      'Content-Type': 'application/json',
    }),
    [authToken],
  );

  const loadAccessData = async () => {
    setLoading(true);
    setError('');
    try {
      const res = await fetch(`${apiBase}/admin/access-requests`, {
        headers: { Authorization: `Bearer ${authToken}` },
      });
      if (!res.ok) throw new Error(`Failed to load admin data (${res.status})`);
      const data: AdminAccessResponse = await res.json();
      setUsers(data.users || []);
      setRequests(data.requests || []);
      const nextDrafts: Record<number, RowDraft> = {};
      for (const u of data.users || []) {
        nextDrafts[u.id] = {
          status: u.status,
          access_granted: u.access_granted,
          review_notes: '',
        };
      }
      setDrafts(nextDrafts);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Unknown error');
    } finally {
      setLoading(false);
    }
  };

  const loadMonitoringData = async (nextOffset = 0, filters: MonitoringFilters = monitoringAppliedFilters) => {
    setMonitoringLoading(true);
    setError('');
    try {
      const params = new URLSearchParams();
      const fromIso = toIsoRangeStart(filters.from);
      const toIso = toIsoRangeEnd(filters.to);
      if (fromIso) params.set('from', fromIso);
      if (toIso) params.set('to', toIso);
      if (filters.ip.trim()) params.set('ip', filters.ip.trim());
      if (filters.userId.trim()) params.set('user_id', filters.userId.trim());
      if (filters.email.trim()) params.set('email', filters.email.trim());
      if (filters.pathContains.trim()) params.set('path_contains', filters.pathContains.trim());
      if (filters.statusCode.trim()) params.set('status_code', filters.statusCode.trim());
      if (filters.outcome) params.set('outcome', filters.outcome);
      if (filters.authenticatedOnly === 'yes') params.set('authenticated_only', 'true');
      if (filters.authenticatedOnly === 'no') params.set('authenticated_only', 'false');
      params.set('limit', String(MONITORING_PAGE_SIZE));
      params.set('offset', String(nextOffset));

      const res = await fetch(`${apiBase}/admin/monitoring/access-events?${params.toString()}`, {
        headers: { Authorization: `Bearer ${authToken}` },
      });
      if (!res.ok) {
        const payload = await res.json().catch(() => ({}));
        throw new Error(payload.detail || `Failed to load monitoring data (${res.status})`);
      }
      const data: AdminAccessMonitoringResponse = await res.json();
      setMonitoring({
        ok: data.ok,
        events: data.events || [],
        summary: data.summary || EMPTY_MONITORING_SUMMARY,
        top_ips: data.top_ips || [],
        limit: data.limit || MONITORING_PAGE_SIZE,
        offset: data.offset || 0,
        has_more: Boolean(data.has_more),
      });
    } catch (e: unknown) {
      setMonitoring((prev) => ({
        ...prev,
        events: [],
        top_ips: [],
        summary: EMPTY_MONITORING_SUMMARY,
        has_more: false,
      }));
      setError(e instanceof Error ? e.message : 'Unknown error');
    } finally {
      setMonitoringLoading(false);
    }
  };

  useEffect(() => {
    void loadAccessData();
    void loadMonitoringData(0, initialMonitoringFilters);
  }, []);

  const refreshAll = async () => {
    await Promise.all([loadAccessData(), loadMonitoringData(monitoring.offset, monitoringAppliedFilters)]);
  };

  const updateDraft = (userId: number, patch: Partial<RowDraft>) => {
    setDrafts((prev) => ({
      ...prev,
      [userId]: { ...(prev[userId] || { status: 'pending', access_granted: false, review_notes: '' }), ...patch },
    }));
  };

  const updateMonitoringDraft = <K extends keyof MonitoringFilters>(key: K, value: MonitoringFilters[K]) => {
    setMonitoringDraftFilters((prev) => ({ ...prev, [key]: value }));
  };

  const applyMonitoringFilters = async () => {
    setMonitoringAppliedFilters(monitoringDraftFilters);
    await loadMonitoringData(0, monitoringDraftFilters);
  };

  const resetMonitoringFilters = async () => {
    const defaults = getDefaultMonitoringFilters();
    setMonitoringDraftFilters(defaults);
    setMonitoringAppliedFilters(defaults);
    await loadMonitoringData(0, defaults);
  };

  const saveAccess = async (user: AdminUser) => {
    const draft = drafts[user.id];
    if (!draft) return;
    setError('');
    setMessage('');
    try {
      const res = await fetch(`${apiBase}/admin/users/${user.id}/access`, {
        method: 'PATCH',
        headers,
        body: JSON.stringify(draft),
      });
      if (!res.ok) {
        const payload = await res.json().catch(() => ({}));
        throw new Error(payload.detail || `Update failed (${res.status})`);
      }
      setMessage(`Updated access for ${user.email}`);
      await refreshAll();
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Unknown error');
    }
  };

  const createSetupLink = async (user: AdminUser) => {
    setError('');
    setMessage('');
    try {
      const res = await fetch(`${apiBase}/admin/users/${user.id}/password-setup-link`, {
        method: 'POST',
        headers: { Authorization: `Bearer ${authToken}` },
      });
      if (!res.ok) {
        const payload = await res.json().catch(() => ({}));
        throw new Error(payload.detail || `Link generation failed (${res.status})`);
      }
      const data = await res.json();
      setSetupLinks((prev) => ({ ...prev, [user.id]: data.setup_url }));
      setMessage(`Password setup link generated and email sent to ${user.email}`);
      await loadMonitoringData(monitoring.offset, monitoringAppliedFilters);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Unknown error');
    }
  };

  const copySetupLink = async (userId: number) => {
    const link = setupLinks[userId];
    if (!link) return;
    await navigator.clipboard.writeText(link);
    setMessage('Setup link copied to clipboard.');
  };

  return (
    <div className="flex-1 overflow-y-auto bg-surface-container-low p-6">
      <div className="mx-auto max-w-7xl space-y-6">
        <div className="flex items-center justify-between">
          <div>
            <h2 className="text-2xl font-headline font-bold text-primary">Admin Access Control</h2>
            <p className="text-sm text-on-surface-variant">Single-admin user approval and access management.</p>
          </div>
          <button
            onClick={() => void refreshAll()}
            className="inline-flex items-center gap-2 rounded-lg border border-outline-variant/30 px-4 py-2 text-sm font-semibold hover:border-primary/30"
          >
            <RefreshCcw size={14} />
            Refresh All
          </button>
        </div>

        {error && <div className="rounded-xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700">{error}</div>}
        {message && <div className="rounded-xl border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-700">{message}</div>}

        <div className="grid gap-4 md:grid-cols-3">
          {[
            {
              id: 'user_management' as const,
              title: 'User management',
              subtitle: 'Approve users, update access, and generate setup links.',
              count: users.length,
            },
            {
              id: 'audit_history' as const,
              title: 'Audit history',
              subtitle: 'Review the access request audit trail and status changes.',
              count: requests.length,
            },
            {
              id: 'access_history' as const,
              title: 'Access history',
              subtitle: 'Inspect IP-based access activity and recent admin-visible traffic.',
              count: monitoring.summary.total,
            },
          ].map((card) => {
            const isActive = activeView === card.id;
            return (
              <button
                key={card.id}
                type="button"
                onClick={() => setActiveView(card.id)}
                className={`rounded-2xl border px-5 py-4 text-left shadow-sm transition ${
                  isActive
                    ? 'border-primary/40 bg-primary/10 text-primary'
                    : 'border-outline-variant/15 bg-surface-container-lowest text-on-surface hover:border-primary/20 hover:bg-surface-container-low'
                }`}
              >
                <div className="flex items-start justify-between gap-4">
                  <div>
                    <div className="text-base font-semibold">{card.title}</div>
                    <p className={`mt-2 text-sm ${isActive ? 'text-primary/80' : 'text-on-surface-variant'}`}>{card.subtitle}</p>
                  </div>
                  <div className={`rounded-full px-3 py-1 text-xs font-semibold ${isActive ? 'bg-primary text-on-primary' : 'bg-surface-container-low text-on-surface-variant'}`}>
                    {card.count}
                  </div>
                </div>
              </button>
            );
          })}
        </div>

        {activeView === 'user_management' && (
          <div className="overflow-hidden rounded-2xl border border-outline-variant/15 bg-surface-container-lowest shadow-sm">
            <div className="border-b border-outline-variant/10 px-4 py-3 font-semibold text-sm text-on-surface">User management ({users.length})</div>
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead className="bg-surface-container-low">
                  <tr className="text-left text-on-surface-variant">
                    <th className="px-4 py-3">User</th>
                    <th className="px-4 py-3">Organization</th>
                    <th className="px-4 py-3">Status</th>
                    <th className="px-4 py-3">Access</th>
                    <th className="px-4 py-3">Notes</th>
                    <th className="px-4 py-3">Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {users.map((u) => {
                    const d = drafts[u.id] || { status: u.status, access_granted: u.access_granted, review_notes: '' };
                    return (
                      <tr key={u.id} className="border-t border-outline-variant/10 align-top">
                        <td className="px-4 py-3">
                          <div className="font-semibold text-on-surface">{u.name}</div>
                          <div className="text-xs text-on-surface-variant">{u.email}</div>
                          <div className="mt-1 text-xs text-on-surface-variant">Password: {u.has_password ? 'Set' : 'Not set'}</div>
                        </td>
                        <td className="px-4 py-3 text-xs text-on-surface-variant">
                          <div>{u.organization || '-'}</div>
                          <div className="mt-1">{u.use_case || '-'}</div>
                        </td>
                        <td className="px-4 py-3">
                          <select
                            value={d.status}
                            onChange={(e) => updateDraft(u.id, { status: e.target.value as RowDraft['status'] })}
                            className="rounded-lg border border-outline-variant/30 px-2 py-1 text-xs"
                          >
                            <option value="pending">Pending</option>
                            <option value="granted">Granted</option>
                            <option value="denied">Denied</option>
                          </select>
                        </td>
                        <td className="px-4 py-3">
                          <label className="inline-flex items-center gap-2 text-xs">
                            <input
                              type="checkbox"
                              checked={d.access_granted}
                              onChange={(e) => updateDraft(u.id, { access_granted: e.target.checked })}
                            />
                            {d.access_granted ? 'Granted' : 'Not granted'}
                          </label>
                        </td>
                        <td className="px-4 py-3">
                          <input
                            value={d.review_notes}
                            onChange={(e) => updateDraft(u.id, { review_notes: e.target.value })}
                            placeholder="Optional note"
                            className="w-full rounded-lg border border-outline-variant/30 px-2 py-1 text-xs"
                          />
                        </td>
                        <td className="space-y-2 px-4 py-3">
                          <button
                            onClick={() => void saveAccess(u)}
                            className="w-full rounded-lg bg-primary px-3 py-1.5 text-xs font-semibold text-on-primary hover:opacity-90"
                          >
                            Save
                          </button>
                          <button
                            disabled={!(d.status === 'granted' && d.access_granted)}
                            onClick={() => void createSetupLink(u)}
                            className="w-full rounded-lg border border-outline-variant/30 px-3 py-1.5 text-xs font-semibold disabled:opacity-50"
                          >
                            Generate Setup Link
                          </button>
                          {setupLinks[u.id] && (
                            <div className="rounded-lg border border-outline-variant/20 bg-surface-container-low p-2">
                              <div className="break-all text-[10px] text-on-surface-variant">{setupLinks[u.id]}</div>
                              <button
                                onClick={() => void copySetupLink(u.id)}
                                className="mt-1 inline-flex items-center gap-1 text-[11px] font-semibold text-primary"
                              >
                                <Copy size={12} />
                                Copy
                              </button>
                            </div>
                          )}
                        </td>
                      </tr>
                    );
                  })}
                  {!loading && users.length === 0 && (
                    <tr>
                      <td colSpan={6} className="px-4 py-8 text-center text-sm text-on-surface-variant">
                        No user requests yet.
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          </div>
        )}

        {activeView === 'audit_history' && (
          <div className="overflow-hidden rounded-2xl border border-outline-variant/15 bg-surface-container-lowest shadow-sm">
            <div className="border-b border-outline-variant/10 px-4 py-3 font-semibold text-sm text-on-surface">
              Audit history ({requests.length})
            </div>
            <div className="max-h-[560px] overflow-y-auto">
              <table className="w-full text-xs">
                <thead className="bg-surface-container-low">
                  <tr className="text-left text-on-surface-variant">
                    <th className="px-4 py-2">Time</th>
                    <th className="px-4 py-2">Email</th>
                    <th className="px-4 py-2">Status</th>
                    <th className="px-4 py-2">Review Notes</th>
                  </tr>
                </thead>
                <tbody>
                  {requests.map((r) => (
                    <tr key={r.id} className="border-t border-outline-variant/10">
                      <td className="px-4 py-2">{r.created_at}</td>
                      <td className="px-4 py-2">{r.email}</td>
                      <td className="px-4 py-2 font-semibold uppercase">{r.status}</td>
                      <td className="px-4 py-2">{r.review_notes || '-'}</td>
                    </tr>
                  ))}
                  {!loading && requests.length === 0 && (
                    <tr>
                      <td colSpan={4} className="px-4 py-6 text-center text-on-surface-variant">
                        No request audit entries yet.
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          </div>
        )}

        {activeView === 'access_history' && (
          <div className="overflow-hidden rounded-2xl border border-outline-variant/15 bg-surface-container-lowest shadow-sm">
          <div className="border-b border-outline-variant/10 px-4 py-3">
            <h3 className="font-semibold text-on-surface">Access history</h3>
            <p className="mt-1 text-xs text-on-surface-variant">
              Review backend-visible traffic, top IP addresses, authenticated activity, and failed requests.
            </p>
          </div>

          <div className="space-y-6 p-4">
            <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-5">
              <div className="rounded-xl border border-outline-variant/15 bg-surface-container-low p-4">
                <div className="text-xs uppercase tracking-wide text-on-surface-variant">Total Events</div>
                <div className="mt-2 text-2xl font-semibold text-on-surface">{monitoring.summary.total}</div>
              </div>
              <div className="rounded-xl border border-outline-variant/15 bg-surface-container-low p-4">
                <div className="text-xs uppercase tracking-wide text-on-surface-variant">Unique IPs</div>
                <div className="mt-2 text-2xl font-semibold text-on-surface">{monitoring.summary.unique_ips}</div>
              </div>
              <div className="rounded-xl border border-outline-variant/15 bg-surface-container-low p-4">
                <div className="text-xs uppercase tracking-wide text-on-surface-variant">Authenticated</div>
                <div className="mt-2 text-2xl font-semibold text-on-surface">{monitoring.summary.authenticated}</div>
              </div>
              <div className="rounded-xl border border-outline-variant/15 bg-surface-container-low p-4">
                <div className="text-xs uppercase tracking-wide text-on-surface-variant">Anonymous</div>
                <div className="mt-2 text-2xl font-semibold text-on-surface">{monitoring.summary.anonymous}</div>
              </div>
              <div className="rounded-xl border border-outline-variant/15 bg-surface-container-low p-4">
                <div className="text-xs uppercase tracking-wide text-on-surface-variant">Failed</div>
                <div className="mt-2 text-2xl font-semibold text-on-surface">{monitoring.summary.failed}</div>
              </div>
            </div>

            <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
              <label className="text-xs text-on-surface-variant">
                From
                <input
                  type="date"
                  value={monitoringDraftFilters.from}
                  onChange={(e) => updateMonitoringDraft('from', e.target.value)}
                  className="mt-1 w-full rounded-lg border border-outline-variant/30 px-3 py-2 text-sm text-on-surface"
                />
              </label>
              <label className="text-xs text-on-surface-variant">
                To
                <input
                  type="date"
                  value={monitoringDraftFilters.to}
                  onChange={(e) => updateMonitoringDraft('to', e.target.value)}
                  className="mt-1 w-full rounded-lg border border-outline-variant/30 px-3 py-2 text-sm text-on-surface"
                />
              </label>
              <label className="text-xs text-on-surface-variant">
                IP Address
                <input
                  value={monitoringDraftFilters.ip}
                  onChange={(e) => updateMonitoringDraft('ip', e.target.value)}
                  placeholder="203.0.113.42"
                  className="mt-1 w-full rounded-lg border border-outline-variant/30 px-3 py-2 text-sm text-on-surface"
                />
              </label>
              <label className="text-xs text-on-surface-variant">
                User ID
                <input
                  value={monitoringDraftFilters.userId}
                  onChange={(e) => updateMonitoringDraft('userId', e.target.value)}
                  placeholder="42"
                  className="mt-1 w-full rounded-lg border border-outline-variant/30 px-3 py-2 text-sm text-on-surface"
                />
              </label>
              <label className="text-xs text-on-surface-variant">
                User Email
                <input
                  value={monitoringDraftFilters.email}
                  onChange={(e) => updateMonitoringDraft('email', e.target.value)}
                  placeholder="user@example.com"
                  className="mt-1 w-full rounded-lg border border-outline-variant/30 px-3 py-2 text-sm text-on-surface"
                />
              </label>
              <label className="text-xs text-on-surface-variant">
                Path Contains
                <input
                  value={monitoringDraftFilters.pathContains}
                  onChange={(e) => updateMonitoringDraft('pathContains', e.target.value)}
                  placeholder="/admin"
                  className="mt-1 w-full rounded-lg border border-outline-variant/30 px-3 py-2 text-sm text-on-surface"
                />
              </label>
              <label className="text-xs text-on-surface-variant">
                Status Code
                <input
                  value={monitoringDraftFilters.statusCode}
                  onChange={(e) => updateMonitoringDraft('statusCode', e.target.value)}
                  placeholder="401"
                  className="mt-1 w-full rounded-lg border border-outline-variant/30 px-3 py-2 text-sm text-on-surface"
                />
              </label>
              <label className="text-xs text-on-surface-variant">
                Outcome
                <select
                  value={monitoringDraftFilters.outcome}
                  onChange={(e) => updateMonitoringDraft('outcome', e.target.value as MonitoringFilters['outcome'])}
                  className="mt-1 w-full rounded-lg border border-outline-variant/30 px-3 py-2 text-sm text-on-surface"
                >
                  <option value="">All outcomes</option>
                  <option value="success">Success</option>
                  <option value="client_error">Client error</option>
                  <option value="server_error">Server error</option>
                </select>
              </label>
            </div>

            <div className="flex flex-wrap items-center gap-3">
              <label className="text-xs text-on-surface-variant">
                Authenticated
                <select
                  value={monitoringDraftFilters.authenticatedOnly}
                  onChange={(e) => updateMonitoringDraft('authenticatedOnly', e.target.value as MonitoringFilters['authenticatedOnly'])}
                  className="mt-1 block rounded-lg border border-outline-variant/30 px-3 py-2 text-sm text-on-surface"
                >
                  <option value="all">All traffic</option>
                  <option value="yes">Authenticated only</option>
                  <option value="no">Anonymous only</option>
                </select>
              </label>
              <button
                onClick={() => void applyMonitoringFilters()}
                className="rounded-lg bg-primary px-4 py-2 text-sm font-semibold text-on-primary hover:opacity-90"
              >
                Apply Filters
              </button>
              <button
                onClick={() => void resetMonitoringFilters()}
                className="rounded-lg border border-outline-variant/30 px-4 py-2 text-sm font-semibold text-on-surface"
              >
                Reset
              </button>
              <button
                onClick={() => void loadMonitoringData(monitoring.offset, monitoringAppliedFilters)}
                className="rounded-lg border border-outline-variant/30 px-4 py-2 text-sm font-semibold text-on-surface"
              >
                Refresh Monitoring
              </button>
              {monitoringLoading && <span className="text-xs text-on-surface-variant">Loading monitoring data...</span>}
            </div>

            <div className="grid gap-4 xl:grid-cols-[320px_minmax(0,1fr)]">
              <div className="rounded-2xl border border-outline-variant/15 bg-surface-container-low p-4">
                <div className="flex items-center justify-between">
                  <h4 className="font-semibold text-on-surface">Top IPs</h4>
                  <span className="text-xs text-on-surface-variant">Current filter set</span>
                </div>
                <div className="mt-4 space-y-3">
                  {monitoring.top_ips.map((item) => (
                    <div key={`${item.ip_address}-${item.last_seen_at}`} className="rounded-xl border border-outline-variant/10 bg-surface-container-lowest p-3">
                      <div className="font-mono text-sm text-on-surface">{item.ip_address}</div>
                      <div className="mt-1 text-xs text-on-surface-variant">Hits: {item.hit_count}</div>
                      <div className="mt-1 text-xs text-on-surface-variant">Last seen: {formatTimestamp(item.last_seen_at)}</div>
                    </div>
                  ))}
                  {!monitoringLoading && monitoring.top_ips.length === 0 && (
                    <div className="rounded-xl border border-dashed border-outline-variant/20 px-3 py-6 text-center text-sm text-on-surface-variant">
                      No IP activity for the current filters.
                    </div>
                  )}
                </div>
              </div>

              <div className="overflow-hidden rounded-2xl border border-outline-variant/15 bg-surface-container-low">
                <div className="border-b border-outline-variant/10 px-4 py-3 font-semibold text-sm text-on-surface">
                  Recent Access Events ({monitoring.summary.total})
                </div>
                <div className="overflow-x-auto">
                  <table className="w-full text-xs">
                    <thead className="bg-surface-container-lowest">
                      <tr className="text-left text-on-surface-variant">
                        <th className="px-4 py-3">Time</th>
                        <th className="px-4 py-3">IP</th>
                        <th className="px-4 py-3">User</th>
                        <th className="px-4 py-3">Route</th>
                        <th className="px-4 py-3">Status</th>
                        <th className="px-4 py-3">User Agent</th>
                        <th className="px-4 py-3">Referrer / Origin</th>
                      </tr>
                    </thead>
                    <tbody>
                      {monitoring.events.map((event) => (
                        <tr key={event.id} className="border-t border-outline-variant/10 align-top">
                          <td className="px-4 py-3 text-on-surface-variant">{formatTimestamp(event.occurred_at)}</td>
                          <td className="px-4 py-3">
                            <div className="font-mono text-[11px] text-on-surface">{event.ip_address || '-'}</div>
                            {(event.forwarded_for || event.real_ip) && (
                              <div className="mt-1 text-[10px] text-on-surface-variant">
                                {event.forwarded_for ? `XFF: ${event.forwarded_for}` : `X-Real-IP: ${event.real_ip}`}
                              </div>
                            )}
                          </td>
                          <td className="px-4 py-3">
                            <div className="font-medium text-on-surface">{event.user_email || 'Anonymous'}</div>
                            <div className="mt-1 text-[10px] text-on-surface-variant">
                              {event.is_authenticated ? `Role: ${event.user_role || 'unknown'}` : 'Unauthenticated'}
                            </div>
                            {event.user_id != null && (
                              <div className="mt-1 text-[10px] text-on-surface-variant">
                                User #{event.user_id}
                                {event.session_id != null ? ` | Session #${event.session_id}` : ''}
                              </div>
                            )}
                          </td>
                          <td className="px-4 py-3">
                            <div className="font-semibold text-on-surface">{event.method}</div>
                            <div className="mt-1 break-all text-on-surface-variant">{event.path}</div>
                            {event.query_string_present && (
                              <div className="mt-1 text-[10px] uppercase tracking-wide text-on-surface-variant">Query string present</div>
                            )}
                          </td>
                          <td className="px-4 py-3">
                            <div className="font-semibold text-on-surface">{event.status_code}</div>
                            <span className={`mt-1 inline-flex rounded-full px-2 py-1 text-[10px] font-semibold uppercase ${outcomeBadgeClass(event.outcome)}`}>
                              {event.outcome.replace('_', ' ')}
                            </span>
                          </td>
                          <td className="px-4 py-3 text-on-surface-variant">
                            <div className="max-w-[220px] break-words">{event.user_agent || '-'}</div>
                          </td>
                          <td className="px-4 py-3 text-on-surface-variant">
                            <div className="max-w-[240px] break-words">{event.referer || '-'}</div>
                            <div className="mt-1 max-w-[240px] break-words text-[10px]">{event.origin || '-'}</div>
                          </td>
                        </tr>
                      ))}
                      {!monitoringLoading && monitoring.events.length === 0 && (
                        <tr>
                          <td colSpan={7} className="px-4 py-8 text-center text-sm text-on-surface-variant">
                            No access events matched the current filters.
                          </td>
                        </tr>
                      )}
                    </tbody>
                  </table>
                </div>

                <div className="flex items-center justify-between border-t border-outline-variant/10 px-4 py-3 text-xs text-on-surface-variant">
                  <span>
                    Showing {monitoring.events.length} event{monitoring.events.length === 1 ? '' : 's'} starting at offset {monitoring.offset}
                  </span>
                  <div className="flex gap-2">
                    <button
                      disabled={monitoring.offset <= 0 || monitoringLoading}
                      onClick={() => void loadMonitoringData(Math.max(0, monitoring.offset - monitoring.limit), monitoringAppliedFilters)}
                      className="rounded-lg border border-outline-variant/30 px-3 py-1.5 font-semibold disabled:opacity-50"
                    >
                      Previous
                    </button>
                    <button
                      disabled={!monitoring.has_more || monitoringLoading}
                      onClick={() => void loadMonitoringData(monitoring.offset + monitoring.limit, monitoringAppliedFilters)}
                      className="rounded-lg border border-outline-variant/30 px-3 py-1.5 font-semibold disabled:opacity-50"
                    >
                      Next
                    </button>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
        )}
      </div>
    </div>
  );
};
