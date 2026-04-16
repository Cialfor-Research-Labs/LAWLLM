import React, { useState } from 'react';

interface RequestAccessPageProps {
  apiBase: string;
  onBackToLogin: () => void;
}

export const RequestAccessPage = ({ apiBase, onBackToLogin }: RequestAccessPageProps) => {
  const [firstName, setFirstName] = useState('');
  const [lastName, setLastName] = useState('');
  const [email, setEmail] = useState('');
  const [organization, setOrganization] = useState('');
  const [useCase, setUseCase] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [message, setMessage] = useState('');

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setError('');
    setMessage('');
    try {
      const res = await fetch(`${apiBase}/auth/request-access`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          first_name: firstName.trim(),
          last_name: lastName.trim(),
          email: email.trim(),
          organization: organization.trim(),
          use_case: useCase.trim(),
        }),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) {
        throw new Error(data.detail || `Request failed (${res.status})`);
      }
      setMessage(data.message || 'Access request submitted.');
      setFirstName('');
      setLastName('');
      setEmail('');
      setOrganization('');
      setUseCase('');
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Unexpected request error.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen flex items-center justify-center bg-surface-container-low p-6">
      <div className="w-full max-w-xl rounded-2xl border border-outline-variant/20 bg-surface-container-lowest p-8 shadow-lg">
        <h1 className="text-2xl font-headline font-bold text-primary">Request Product Access</h1>
        <p className="mt-1 text-sm text-on-surface-variant">Submit your details for admin approval.</p>

        {error && <div className="mt-4 rounded-lg border border-rose-200 bg-rose-50 px-3 py-2 text-sm text-rose-700">{error}</div>}
        {message && <div className="mt-4 rounded-lg border border-emerald-200 bg-emerald-50 px-3 py-2 text-sm text-emerald-700">{message}</div>}

        <form onSubmit={submit} className="mt-6 space-y-4">
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-xs font-bold uppercase tracking-[0.12em] text-on-surface-variant mb-1">First Name</label>
              <input
                required
                value={firstName}
                onChange={(e) => setFirstName(e.target.value)}
                className="w-full rounded-xl border border-outline-variant/30 px-4 py-3 text-sm"
              />
            </div>
            <div>
              <label className="block text-xs font-bold uppercase tracking-[0.12em] text-on-surface-variant mb-1">Last Name</label>
              <input
                required
                value={lastName}
                onChange={(e) => setLastName(e.target.value)}
                className="w-full rounded-xl border border-outline-variant/30 px-4 py-3 text-sm"
              />
            </div>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-xs font-bold uppercase tracking-[0.12em] text-on-surface-variant mb-1">Email</label>
              <input
                required
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                className="w-full rounded-xl border border-outline-variant/30 px-4 py-3 text-sm"
              />
            </div>
            <div>
              <label className="block text-xs font-bold uppercase tracking-[0.12em] text-on-surface-variant mb-1">Organization</label>
              <input
                required
                value={organization}
                onChange={(e) => setOrganization(e.target.value)}
                className="w-full rounded-xl border border-outline-variant/30 px-4 py-3 text-sm"
              />
            </div>
          </div>
          <div>
            <label className="block text-xs font-bold uppercase tracking-[0.12em] text-on-surface-variant mb-1">Use Case</label>
            <textarea
              required
              value={useCase}
              onChange={(e) => setUseCase(e.target.value)}
              rows={4}
              className="w-full rounded-xl border border-outline-variant/30 px-4 py-3 text-sm resize-none"
              placeholder="Describe how you plan to use the product."
            />
          </div>
          <button
            type="submit"
            disabled={loading}
            className="w-full rounded-xl bg-primary px-4 py-3 text-sm font-semibold text-on-primary hover:opacity-90 disabled:opacity-50"
          >
            {loading ? 'Submitting...' : 'Submit Access Request'}
          </button>
        </form>

        <button onClick={onBackToLogin} className="mt-5 text-sm font-semibold text-primary hover:underline">
          Back to Login
        </button>
      </div>
    </div>
  );
};
