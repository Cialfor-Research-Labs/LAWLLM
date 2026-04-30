import React, { useState } from 'react';
import { ArrowRight, Lock, Mail, ShieldCheck } from 'lucide-react';

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

interface ApiMessageResponse {
  ok: boolean;
  message?: string;
  detail?: string;
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
  const [forgotPasswordLoading, setForgotPasswordLoading] = useState(false);
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

  const handleForgotPassword = async () => {
    const cleanEmail = email.trim();
    setError('');
    setInfo('');
    if (!cleanEmail) {
      setError('Enter your email address first to receive a password setup link.');
      return;
    }

    setForgotPasswordLoading(true);
    try {
      const res = await fetch(`${apiBase}/auth/forgot-password`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email: cleanEmail }),
      });
      const data: ApiMessageResponse = await res.json().catch(() => ({}));
      if (!res.ok) {
        throw new Error(data.detail || `Unable to process forgot password (${res.status})`);
      }
      setInfo(data.message || 'Password setup link sent to your email address.');
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Unexpected forgot password error.');
    } finally {
      setForgotPasswordLoading(false);
    }
  };

  return (
    <div className="flex min-h-screen items-center justify-center px-4 py-8 sm:px-6">
      <div className="grid w-full max-w-6xl overflow-hidden rounded-[28px] border border-outline-variant/70 bg-surface-variant shadow-ambient lg:grid-cols-[1.05fr_0.95fr]">
        <div className="bg-secondary px-8 py-10 text-white sm:px-10 lg:px-12">
          <div className="max-w-md">
            <div className="inline-flex items-center gap-2 rounded-full bg-white/10 px-3 py-1 text-xs font-medium text-white/85">
              <ShieldCheck size={14} />
              Trusted legal workspace
            </div>
            <h1 className="mt-6 text-4xl font-semibold leading-tight">Legal AI, redesigned to feel calm and capable.</h1>
            <p className="mt-4 text-sm leading-7 text-white/75">
              Sign in to continue your legal research, notice drafting, and guided issue analysis in one place. No workflow changes, just a cleaner experience.
            </p>

            <div className="mt-8 grid gap-4 sm:grid-cols-3">
              <div className="rounded-2xl bg-white/8 px-4 py-4">
                <div className="text-sm font-medium">Legal chat</div>
                <div className="mt-1 text-xs text-white/70">Structured interview flow</div>
              </div>
              <div className="rounded-2xl bg-white/8 px-4 py-4">
                <div className="text-sm font-medium">Notice drafting</div>
                <div className="mt-1 text-xs text-white/70">Professional output</div>
              </div>
              <div className="rounded-2xl bg-white/8 px-4 py-4">
                <div className="text-sm font-medium">Secure access</div>
                <div className="mt-1 text-xs text-white/70">Admin-approved workspace</div>
              </div>
            </div>
          </div>
        </div>

        <div className="bg-surface-container-lowest px-8 py-10 sm:px-10 lg:px-12">
          <div className="mx-auto max-w-md">
            <p className="section-kicker">Sign in</p>
            <h2 className="mt-1 text-3xl font-semibold text-on-surface">Access your workspace</h2>
            <p className="mt-2 text-sm leading-7 text-on-surface-variant">
              Use the email address approved for your account.
            </p>

            {error ? (
              <div className="mt-5 rounded-2xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700">{error}</div>
            ) : null}
            {info ? (
              <div className="mt-5 rounded-2xl border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-700">{info}</div>
            ) : null}

            <form onSubmit={handleSubmit} className="mt-8 space-y-5">
              <div>
                <label className="field-label">Email</label>
                <div className="relative">
                  <Mail size={16} className="pointer-events-none absolute left-4 top-1/2 -translate-y-1/2 text-on-surface-variant" />
                  <input
                    type="email"
                    required
                    value={email}
                    onChange={(e) => setEmail(e.target.value)}
                    className="text-field pl-11"
                    placeholder="you@example.com"
                  />
                </div>
              </div>

              <div>
                <label className="field-label">Password</label>
                <div className="relative">
                  <Lock size={16} className="pointer-events-none absolute left-4 top-1/2 -translate-y-1/2 text-on-surface-variant" />
                  <input
                    type="password"
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    className="text-field pl-11"
                    placeholder="Enter your password"
                  />
                </div>
                <div className="mt-2 flex justify-end">
                  <button
                    type="button"
                    onClick={handleForgotPassword}
                    disabled={forgotPasswordLoading}
                    className="text-sm font-medium text-primary transition hover:opacity-80 disabled:opacity-50"
                  >
                    {forgotPasswordLoading ? 'Sending link...' : 'Forgot password?'}
                  </button>
                </div>
              </div>

              <button type="submit" disabled={loading} className="primary-button w-full justify-center">
                {loading ? 'Signing in...' : 'Sign in'}
                {!loading ? <ArrowRight size={16} /> : null}
              </button>
            </form>

            <div className="mt-8 rounded-2xl border border-outline-variant/70 bg-surface-container-low px-5 py-5">
              <div className="text-sm font-medium text-on-surface">Need access first?</div>
              <p className="mt-1 text-sm leading-7 text-on-surface-variant">
                Request workspace access if your account has not been approved yet.
              </p>
              <button type="button" onClick={onShowRequestAccess} className="secondary-button mt-4 w-full justify-center">
                Request access
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};
