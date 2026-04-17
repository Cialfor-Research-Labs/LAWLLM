import React, { useState } from 'react';

interface AuthUser {
  id: number;
  name: string;
  email: string;
  organization: string;
  use_case: string;
  advocate_address: string;
  advocate_mobile: string;
  role: 'admin' | 'user';
  status: 'pending' | 'granted' | 'denied';
  access_granted: boolean;
  created_at: string;
  updated_at: string;
}

interface LoginResponse {
  ok: boolean;
  state: 'success' | 'pending_access' | 'access_denied' | 'password_setup_required';
  message: string;
  token?: string;
  user?: AuthUser;
}

interface LoginPageProps {
  apiBase: string;
  onLoginSuccess: (token: string, user: AuthUser) => void;
  onShowRequestAccess: () => void;
}

export const LoginPage = ({ apiBase, onLoginSuccess, onShowRequestAccess }: LoginPageProps) => {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [info, setInfo] = useState('');

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setError('');
    setInfo('');
    try {
      const res = await fetch(`${apiBase}/auth/login`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email: email.trim(), password }),
      });
      const data: LoginResponse | { detail?: string } = await res.json().catch(() => ({}));
      if (!res.ok) {
        const message = (data as { detail?: string }).detail || `Login failed (${res.status})`;
        throw new Error(message);
      }

      const payload = data as LoginResponse;
      if (payload.state === 'success' && payload.token && payload.user) {
        onLoginSuccess(payload.token, payload.user);
        return;
      }
      if (payload.state === 'password_setup_required') {
        setInfo(`${payload.message} Use your setup link to create a password.`);
        return;
      }
      setInfo(payload.message || 'Login blocked by current access state.');
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Unexpected login error.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen flex items-center justify-center bg-surface-container-low p-6">
      <div className="w-full max-w-md rounded-2xl border border-outline-variant/20 bg-surface-container-lowest p-8 shadow-lg">
        <h1 className="text-2xl font-headline font-bold text-primary">Legal AI Login</h1>
        <p className="mt-1 text-sm text-on-surface-variant">Single-admin access-controlled workspace.</p>

        {error && <div className="mt-4 rounded-lg border border-rose-200 bg-rose-50 px-3 py-2 text-sm text-rose-700">{error}</div>}
        {info && <div className="mt-4 rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-700">{info}</div>}

        <form onSubmit={handleSubmit} className="mt-6 space-y-4">
          <div>
            <label className="block text-xs font-bold uppercase tracking-[0.12em] text-on-surface-variant mb-1">Email</label>
            <input
              type="email"
              required
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              className="w-full rounded-xl border border-outline-variant/30 px-4 py-3 text-sm"
              placeholder="you@example.com"
            />
          </div>
          <div>
            <label className="block text-xs font-bold uppercase tracking-[0.12em] text-on-surface-variant mb-1">Password</label>
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="w-full rounded-xl border border-outline-variant/30 px-4 py-3 text-sm"
              placeholder="Enter your password"
            />
          </div>

          <button
            type="submit"
            disabled={loading}
            className="w-full rounded-xl bg-primary px-4 py-3 text-sm font-semibold text-on-primary hover:opacity-90 disabled:opacity-50"
          >
            {loading ? 'Signing in...' : 'Sign In'}
          </button>
        </form>

        <div className="mt-6 border-t border-outline-variant/15 pt-4">
          <div className="rounded-xl border border-primary/20 bg-primary/5 px-4 py-3 text-sm text-on-surface">
            <p className="font-semibold text-primary">Testing Credentials Only</p>
            <p className="mt-2">
              Test email: <span className="font-semibold">test@gmail.com</span>
            </p>
            <p className="mt-1">
              Test password: <span className="font-semibold">Lawyertest@123</span>
            </p>
          </div>
        </div>
      </div>
    </div>
  );
};
