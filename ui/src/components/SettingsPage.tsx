import React, { useEffect, useMemo, useState } from 'react';
import { CheckCircle2, Loader2 } from 'lucide-react';

interface SettingsUser {
  id: number;
  name: string;
  email: string;
  organization: string;
  use_case: string;
  role: 'admin' | 'user';
  status: 'pending' | 'granted' | 'denied';
  access_granted: boolean;
  created_at: string;
  updated_at: string;
}

interface SettingsPageProps {
  authToken: string;
  currentUser: SettingsUser;
  onUserUpdated: (user: SettingsUser) => void;
  activeSection: 'details' | 'password';
}

interface UpdateProfileResponse {
  ok: boolean;
  message: string;
  user: SettingsUser;
}

interface ApiMessageResponse {
  ok: boolean;
  message: string;
}

function getApiBase(): string {
  const configured = import.meta.env.VITE_API_BASE_URL?.trim();
  if (configured) {
    return configured.replace(/\/$/, '');
  }
  return '/api';
}

export const SettingsPage = ({ authToken, currentUser, onUserUpdated, activeSection }: SettingsPageProps) => {
  const apiBase = useMemo(() => getApiBase(), []);
  const [name, setName] = useState(currentUser.name || '');
  const [organization, setOrganization] = useState(currentUser.organization || '');
  const [useCase, setUseCase] = useState(currentUser.use_case || '');
  const [profileLoading, setProfileLoading] = useState(false);
  const [profileError, setProfileError] = useState('');
  const [profileMessage, setProfileMessage] = useState('');

  const [currentPassword, setCurrentPassword] = useState('');
  const [newPassword, setNewPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [passwordLoading, setPasswordLoading] = useState(false);
  const [passwordError, setPasswordError] = useState('');
  const [passwordMessage, setPasswordMessage] = useState('');

  useEffect(() => {
    setName(currentUser.name || '');
    setOrganization(currentUser.organization || '');
    setUseCase(currentUser.use_case || '');
  }, [currentUser]);

  const saveProfile = async (e: React.FormEvent) => {
    e.preventDefault();
    setProfileError('');
    setProfileMessage('');

    const cleanName = name.trim();
    if (cleanName.length < 2) {
      setProfileError('Name must be at least 2 characters.');
      return;
    }

    setProfileLoading(true);
    try {
      const res = await fetch(`${apiBase}/auth/me`, {
        method: 'PATCH',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${authToken}`,
        },
        body: JSON.stringify({
          name: cleanName,
          organization: organization.trim(),
          use_case: useCase.trim(),
        }),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) {
        throw new Error(data.detail || `Unable to update profile (${res.status})`);
      }
      const payload = data as UpdateProfileResponse;
      onUserUpdated(payload.user);
      setProfileMessage(payload.message || 'Profile updated successfully.');
    } catch (err: unknown) {
      setProfileError(err instanceof Error ? err.message : 'Unexpected error while updating profile.');
    } finally {
      setProfileLoading(false);
    }
  };

  const changePassword = async (e: React.FormEvent) => {
    e.preventDefault();
    setPasswordError('');
    setPasswordMessage('');

    if (newPassword.length < 8) {
      setPasswordError('New password must be at least 8 characters.');
      return;
    }
    if (newPassword !== confirmPassword) {
      setPasswordError('New password and confirm password do not match.');
      return;
    }

    setPasswordLoading(true);
    try {
      const res = await fetch(`${apiBase}/auth/change-password`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          Authorization: `Bearer ${authToken}`,
        },
        body: JSON.stringify({
          current_password: currentPassword,
          new_password: newPassword,
        }),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) {
        throw new Error(data.detail || `Unable to change password (${res.status})`);
      }
      const payload = data as ApiMessageResponse;
      setPasswordMessage(payload.message || 'Password changed successfully.');
      setCurrentPassword('');
      setNewPassword('');
      setConfirmPassword('');
    } catch (err: unknown) {
      setPasswordError(err instanceof Error ? err.message : 'Unexpected error while changing password.');
    } finally {
      setPasswordLoading(false);
    }
  };

  return (
    <div className="flex-1 overflow-y-auto bg-surface-container-low p-8">
      <div className="max-w-4xl space-y-8">
        <div>
          <h2 className="text-2xl font-headline font-bold text-primary">Settings</h2>
          <p className="text-sm text-on-surface-variant mt-1">
            {activeSection === 'details'
              ? 'Manage your profile details (email cannot be edited).'
              : 'Reset your account password securely.'}
          </p>
        </div>

        {activeSection === 'details' ? (
          <section className="rounded-2xl border border-outline-variant/15 bg-white p-6 shadow-sm">
            <h3 className="text-lg font-semibold text-on-surface">Profile Details</h3>
            <p className="text-xs text-on-surface-variant mt-1">Email is fixed and cannot be changed.</p>

            {profileError && (
              <div className="mt-4 rounded-lg border border-rose-200 bg-rose-50 px-3 py-2 text-sm text-rose-700">
                {profileError}
              </div>
            )}
            {profileMessage && (
              <div className="mt-4 flex items-center gap-2 rounded-lg border border-emerald-200 bg-emerald-50 px-3 py-2 text-sm text-emerald-700">
                <CheckCircle2 size={14} />
                {profileMessage}
              </div>
            )}

            <form onSubmit={saveProfile} className="mt-5 grid grid-cols-1 md:grid-cols-2 gap-4">
              <div>
                <label className="block text-xs font-bold uppercase tracking-[0.12em] text-on-surface-variant mb-2">Full Name</label>
                <input
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  className="w-full rounded-xl border border-outline-variant/30 px-4 py-3 text-sm"
                  required
                />
              </div>
              <div>
                <label className="block text-xs font-bold uppercase tracking-[0.12em] text-on-surface-variant mb-2">Email</label>
                <input
                  value={currentUser.email}
                  disabled
                  className="w-full rounded-xl border border-outline-variant/20 bg-surface-container-low px-4 py-3 text-sm text-on-surface-variant cursor-not-allowed"
                />
              </div>
              <div>
                <label className="block text-xs font-bold uppercase tracking-[0.12em] text-on-surface-variant mb-2">Organization</label>
                <input
                  value={organization}
                  onChange={(e) => setOrganization(e.target.value)}
                  className="w-full rounded-xl border border-outline-variant/30 px-4 py-3 text-sm"
                  placeholder="Your organization"
                />
              </div>
              <div>
                <label className="block text-xs font-bold uppercase tracking-[0.12em] text-on-surface-variant mb-2">Use Case</label>
                <input
                  value={useCase}
                  onChange={(e) => setUseCase(e.target.value)}
                  className="w-full rounded-xl border border-outline-variant/30 px-4 py-3 text-sm"
                  placeholder="How you use this platform"
                />
              </div>
              <div className="md:col-span-2">
                <button
                  type="submit"
                  disabled={profileLoading}
                  className="inline-flex items-center gap-2 rounded-xl bg-primary px-4 py-2.5 text-sm font-semibold text-white hover:opacity-90 disabled:opacity-60"
                >
                  {profileLoading && <Loader2 size={14} className="animate-spin" />}
                  Save Details
                </button>
              </div>
            </form>
          </section>
        ) : (
          <section className="rounded-2xl border border-outline-variant/15 bg-white p-6 shadow-sm">
            <h3 className="text-lg font-semibold text-on-surface">Change Password</h3>
            <p className="text-xs text-on-surface-variant mt-1">Use at least 8 characters.</p>

            {passwordError && (
              <div className="mt-4 rounded-lg border border-rose-200 bg-rose-50 px-3 py-2 text-sm text-rose-700">
                {passwordError}
              </div>
            )}
            {passwordMessage && (
              <div className="mt-4 flex items-center gap-2 rounded-lg border border-emerald-200 bg-emerald-50 px-3 py-2 text-sm text-emerald-700">
                <CheckCircle2 size={14} />
                {passwordMessage}
              </div>
            )}

            <form onSubmit={changePassword} className="mt-5 grid grid-cols-1 md:grid-cols-3 gap-4">
              <div>
                <label className="block text-xs font-bold uppercase tracking-[0.12em] text-on-surface-variant mb-2">Current Password</label>
                <input
                  type="password"
                  value={currentPassword}
                  onChange={(e) => setCurrentPassword(e.target.value)}
                  className="w-full rounded-xl border border-outline-variant/30 px-4 py-3 text-sm"
                  required
                />
              </div>
              <div>
                <label className="block text-xs font-bold uppercase tracking-[0.12em] text-on-surface-variant mb-2">New Password</label>
                <input
                  type="password"
                  value={newPassword}
                  onChange={(e) => setNewPassword(e.target.value)}
                  className="w-full rounded-xl border border-outline-variant/30 px-4 py-3 text-sm"
                  required
                />
              </div>
              <div>
                <label className="block text-xs font-bold uppercase tracking-[0.12em] text-on-surface-variant mb-2">Confirm Password</label>
                <input
                  type="password"
                  value={confirmPassword}
                  onChange={(e) => setConfirmPassword(e.target.value)}
                  className="w-full rounded-xl border border-outline-variant/30 px-4 py-3 text-sm"
                  required
                />
              </div>
              <div className="md:col-span-3">
                <button
                  type="submit"
                  disabled={passwordLoading}
                  className="inline-flex items-center gap-2 rounded-xl bg-primary px-4 py-2.5 text-sm font-semibold text-white hover:opacity-90 disabled:opacity-60"
                >
                  {passwordLoading && <Loader2 size={14} className="animate-spin" />}
                  Change Password
                </button>
              </div>
            </form>
          </section>
        )}
      </div>
    </div>
  );
};
