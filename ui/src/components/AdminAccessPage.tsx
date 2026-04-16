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

export const AdminAccessPage = ({ apiBase, authToken }: { apiBase: string; authToken: string }) => {
  const [users, setUsers] = useState<AdminUser[]>([]);
  const [requests, setRequests] = useState<AdminRequestAudit[]>([]);
  const [drafts, setDrafts] = useState<Record<number, RowDraft>>({});
  const [setupLinks, setSetupLinks] = useState<Record<number, string>>({});
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [message, setMessage] = useState('');

  const headers = useMemo(
    () => ({
      Authorization: `Bearer ${authToken}`,
      'Content-Type': 'application/json',
    }),
    [authToken],
  );

  const loadData = async () => {
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

  useEffect(() => {
    loadData();
  }, []);

  const updateDraft = (userId: number, patch: Partial<RowDraft>) => {
    setDrafts((prev) => ({
      ...prev,
      [userId]: { ...(prev[userId] || { status: 'pending', access_granted: false, review_notes: '' }), ...patch },
    }));
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
      await loadData();
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
    <div className="flex-1 overflow-y-auto p-6 bg-surface-container-low">
      <div className="max-w-7xl mx-auto space-y-6">
        <div className="flex items-center justify-between">
          <div>
            <h2 className="text-2xl font-headline font-bold text-primary">Admin Access Control</h2>
            <p className="text-sm text-on-surface-variant">Single-admin user approval and access management.</p>
          </div>
          <button
            onClick={loadData}
            className="inline-flex items-center gap-2 rounded-lg border border-outline-variant/30 px-4 py-2 text-sm font-semibold hover:border-primary/30"
          >
            <RefreshCcw size={14} />
            Refresh
          </button>
        </div>

        {error && <div className="rounded-xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700">{error}</div>}
        {message && <div className="rounded-xl border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-700">{message}</div>}

        <div className="rounded-2xl border border-outline-variant/15 bg-surface-container-lowest shadow-sm overflow-hidden">
          <div className="px-4 py-3 border-b border-outline-variant/10 font-semibold text-sm text-on-surface">
            Users ({users.length})
          </div>
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
                        <div className="text-xs text-on-surface-variant mt-1">
                          Password: {u.has_password ? 'Set' : 'Not set'}
                        </div>
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
                      <td className="px-4 py-3 space-y-2">
                        <button
                          onClick={() => saveAccess(u)}
                          className="w-full rounded-lg bg-primary px-3 py-1.5 text-xs font-semibold text-white hover:opacity-90"
                        >
                          Save
                        </button>
                        <button
                          disabled={!(d.status === 'granted' && d.access_granted)}
                          onClick={() => createSetupLink(u)}
                          className="w-full rounded-lg border border-outline-variant/30 px-3 py-1.5 text-xs font-semibold disabled:opacity-50"
                        >
                          Generate Setup Link
                        </button>
                        {setupLinks[u.id] && (
                          <div className="rounded-lg border border-outline-variant/20 bg-surface-container-low p-2">
                            <div className="text-[10px] text-on-surface-variant break-all">{setupLinks[u.id]}</div>
                            <button
                              onClick={() => copySetupLink(u.id)}
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

        <div className="rounded-2xl border border-outline-variant/15 bg-surface-container-lowest shadow-sm overflow-hidden">
          <div className="px-4 py-3 border-b border-outline-variant/10 font-semibold text-sm text-on-surface">
            Request Audit ({requests.length})
          </div>
          <div className="max-h-[280px] overflow-y-auto">
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
                    <td className="px-4 py-2 uppercase font-semibold">{r.status}</td>
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
      </div>
    </div>
  );
};
