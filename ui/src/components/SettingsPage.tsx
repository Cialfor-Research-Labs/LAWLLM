import React, { useEffect, useMemo, useState } from 'react';
import { CheckCircle2, Loader2, Lock, Mail } from 'lucide-react';

interface SettingsUser {
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

function FieldLabel({
  children,
  required = false,
}: {
  children: React.ReactNode;
  required?: boolean;
}) {
  return (
    <label className="field-label">
      {children}
      {required ? <span className="field-required">*</span> : null}
    </label>
  );
}

export const SettingsPage = ({ authToken, currentUser, onUserUpdated, activeSection }: SettingsPageProps) => {
  const apiBase = useMemo(() => getApiBase(), []);
  const [name, setName] = useState(currentUser.name || '');
  const [organization, setOrganization] = useState(currentUser.organization || '');
  const [useCase, setUseCase] = useState(currentUser.use_case || '');
  const [advocateAddress, setAdvocateAddress] = useState(currentUser.advocate_address || '');
  const [advocateMobile, setAdvocateMobile] = useState(currentUser.advocate_mobile || '');
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
    setAdvocateAddress(currentUser.advocate_address || '');
    setAdvocateMobile(currentUser.advocate_mobile || '');
  }, [currentUser]);

  useEffect(() => {
    if (!profileMessage) return;
    const timeout = window.setTimeout(() => setProfileMessage(''), 3200);
    return () => window.clearTimeout(timeout);
  }, [profileMessage]);

  useEffect(() => {
    if (!passwordMessage) return;
    const timeout = window.setTimeout(() => setPasswordMessage(''), 3200);
    return () => window.clearTimeout(timeout);
  }, [passwordMessage]);

  const saveProfile = async (e: React.FormEvent) => {
    e.preventDefault();
    setProfileError('');
    setProfileMessage('');

    const cleanName = name.trim();
    if (cleanName.length < 2) {
      setProfileError('Name must be at least 2 characters.');
      return;
    }
    if (advocateAddress.trim().length < 5) {
      setProfileError('Advocate address is required.');
      return;
    }
    if (advocateMobile.trim().length < 8) {
      setProfileError('Advocate mobile is required.');
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
          advocate_address: advocateAddress.trim(),
          advocate_mobile: advocateMobile.trim(),
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
    <div className="flex-1 overflow-y-auto px-4 py-6 sm:px-6 lg:px-8">
      <div className="mx-auto max-w-5xl space-y-6">
        {(profileMessage || passwordMessage) ? (
          <div className="fixed right-4 top-20 z-50">
            <div className="flex items-center gap-2 rounded-2xl border border-primary/20 bg-surface-container-lowest px-4 py-3 text-sm text-primary shadow-ambient">
              <CheckCircle2 size={16} />
              {profileMessage || passwordMessage}
            </div>
          </div>
        ) : null}

        <div className="flex flex-col gap-2">
          <p className="section-kicker">Settings</p>
          <h2 className="text-3xl font-semibold text-secondary">
            {activeSection === 'details' ? 'Profile details' : 'Password and account security'}
          </h2>
          <p className="max-w-2xl text-sm leading-7 text-on-surface-variant">
            {activeSection === 'details'
              ? 'Update your advocate identity and workspace profile. Email stays locked so account ownership remains clear.'
              : 'Change your password without affecting any existing documents, chats, or saved work.'}
          </p>
        </div>

        {activeSection === 'details' ? (
          <section className="app-shell-panel overflow-hidden">
            <div className="border-b border-outline-variant/70 px-6 py-5">
              <h3 className="text-lg font-semibold text-on-surface">Personal and professional profile</h3>
              <p className="mt-1 text-sm text-on-surface-variant">
                Keep these details current so generated notices use the correct advocate identity.
              </p>
            </div>

            {profileError ? (
              <div className="mx-6 mt-6 rounded-2xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700">
                {profileError}
              </div>
            ) : null}

            <form onSubmit={saveProfile} className="space-y-6 px-6 py-6">
              <div className="grid gap-6 lg:grid-cols-[1.1fr_0.9fr]">
                <div className="app-shell-panel bg-surface-container-low px-5 py-5">
                  <div className="mb-4">
                    <p className="section-kicker">Identity</p>
                    <h4 className="mt-1 text-base font-semibold text-on-surface">Core profile</h4>
                  </div>
                  <div className="grid gap-4 md:grid-cols-2">
                    <div>
                      <FieldLabel>Full name</FieldLabel>
                      <input
                        value={name}
                        onChange={(e) => setName(e.target.value)}
                        className="text-field"
                        required
                      />
                    </div>
                    <div>
                      <FieldLabel>Email</FieldLabel>
                      <div className="flex items-center gap-3 rounded-2xl border border-outline-variant/70 bg-surface-container px-4 py-3 text-sm text-on-surface-variant">
                        <Lock size={16} className="text-primary" />
                        <Mail size={16} className="text-on-surface-variant" />
                        <span className="truncate">{currentUser.email}</span>
                      </div>
                    </div>
                    <div>
                      <FieldLabel>Organization</FieldLabel>
                      <input
                        value={organization}
                        onChange={(e) => setOrganization(e.target.value)}
                        className="text-field"
                        placeholder="Your organization"
                      />
                    </div>
                    <div>
                      <FieldLabel>Use case</FieldLabel>
                      <input
                        value={useCase}
                        onChange={(e) => setUseCase(e.target.value)}
                        className="text-field"
                        placeholder="How you use this platform"
                      />
                    </div>
                  </div>
                </div>

                <div className="app-shell-panel bg-surface-container-low px-5 py-5">
                  <div className="mb-4">
                    <p className="section-kicker">Notice drafting</p>
                    <h4 className="mt-1 text-base font-semibold text-on-surface">Advocate details</h4>
                  </div>
                  <div className="space-y-4">
                    <div>
                      <FieldLabel required>Advocate address</FieldLabel>
                      <input
                        value={advocateAddress}
                        onChange={(e) => setAdvocateAddress(e.target.value)}
                        className="text-field"
                        placeholder="Chamber or correspondence address"
                        required
                      />
                    </div>
                    <div>
                      <FieldLabel required>Advocate mobile</FieldLabel>
                      <input
                        value={advocateMobile}
                        onChange={(e) => setAdvocateMobile(e.target.value)}
                        className="text-field"
                        placeholder="e.g. +91 9876543210"
                        required
                      />
                    </div>
                    <div className="rounded-2xl border border-outline-variant/70 bg-surface-container px-4 py-3 text-sm text-on-surface-variant">
                      These fields are required before the notice generator can create a final legal notice.
                    </div>
                  </div>
                </div>
              </div>

              <div className="flex justify-end">
                <button type="submit" disabled={profileLoading} className="primary-button min-w-40">
                  {profileLoading ? <Loader2 size={16} className="animate-spin" /> : null}
                  Save details
                </button>
              </div>
            </form>
          </section>
        ) : (
          <section className="app-shell-panel overflow-hidden">
            <div className="border-b border-outline-variant/70 px-6 py-5">
              <h3 className="text-lg font-semibold text-on-surface">Change password</h3>
              <p className="mt-1 text-sm text-on-surface-variant">Use at least 8 characters and keep it unique to this workspace.</p>
            </div>

            {passwordError ? (
              <div className="mx-6 mt-6 rounded-2xl border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700">
                {passwordError}
              </div>
            ) : null}

            <form onSubmit={changePassword} className="space-y-6 px-6 py-6">
              <div className="grid gap-4 md:grid-cols-3">
                <div>
                  <FieldLabel>Current password</FieldLabel>
                  <input
                    type="password"
                    value={currentPassword}
                    onChange={(e) => setCurrentPassword(e.target.value)}
                    className="text-field"
                    required
                  />
                </div>
                <div>
                  <FieldLabel>New password</FieldLabel>
                  <input
                    type="password"
                    value={newPassword}
                    onChange={(e) => setNewPassword(e.target.value)}
                    className="text-field"
                    required
                  />
                </div>
                <div>
                  <FieldLabel>Confirm password</FieldLabel>
                  <input
                    type="password"
                    value={confirmPassword}
                    onChange={(e) => setConfirmPassword(e.target.value)}
                    className="text-field"
                    required
                  />
                </div>
              </div>

              <div className="flex justify-end">
                <button type="submit" disabled={passwordLoading} className="primary-button min-w-48">
                  {passwordLoading ? <Loader2 size={16} className="animate-spin" /> : null}
                  Change password
                </button>
              </div>
            </form>
          </section>
        )}
      </div>
    </div>
  );
};
