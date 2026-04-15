/**
 * @license
 * SPDX-License-Identifier: Apache-2.0
 */

import React, { useEffect, useMemo, useState } from 'react';
import { Loader2, Search } from 'lucide-react';
import { motion, AnimatePresence } from 'motion/react';
import { Sidebar, Header } from './components/Layout';
import { DocumentAnalyzer } from './components/DocumentAnalyzer';
import { LegalChat } from './components/LegalChat';
import { DocumentGenerator } from './components/DocumentGenerator';
import { WinPredictor } from './components/WinPredictor';
import { SettingsPage } from './components/SettingsPage';
import { LoginPage } from './components/auth/LoginPage';
import { RequestAccessPage } from './components/auth/RequestAccessPage';
import { SetPasswordPage } from './components/auth/SetPasswordPage';
import { AdminAccessPage } from './components/AdminAccessPage';

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

interface ChatHistoryItem {
  session_id: string;
  title: string;
  last_message_at: string;
  message_count: number;
  preview?: string;
}

interface GeneratorHistoryItem {
  id: string;
  title: string;
  created_at: string;
  preview?: string;
}

const ACTIVE_TAB_STORAGE_KEY = 'vidhi_active_tab';
const ACTIVE_CHAT_SESSION_STORAGE_KEY = 'vidhi_active_chat_session';
const ALLOWED_TABS = new Set(['chat', 'generator', 'analyzer', 'predictor', 'admin', 'settings']);

function getInitialActiveTab(): string {
  const stored = (localStorage.getItem(ACTIVE_TAB_STORAGE_KEY) || '').trim().toLowerCase();
  return ALLOWED_TABS.has(stored) ? stored : 'generator';
}

function getInitialActiveChatSessionId(): string | null {
  try {
    const stored = (sessionStorage.getItem(ACTIVE_CHAT_SESSION_STORAGE_KEY) || '').trim();
    return stored || null;
  } catch {
    return null;
  }
}

function getApiBase(): string {
  const configured = import.meta.env.VITE_API_BASE_URL?.trim();
  if (configured) {
    return configured.replace(/\/$/, '');
  }
  return '/api';
}

export default function App() {
  const apiBase = useMemo(() => getApiBase(), []);
  const [authToken, setAuthToken] = useState<string | null>(() => localStorage.getItem('vidhi_auth_token'));
  const [currentUser, setCurrentUser] = useState<AuthUser | null>(null);
  const [authLoading, setAuthLoading] = useState<boolean>(Boolean(localStorage.getItem('vidhi_auth_token')));
  const [authView, setAuthView] = useState<'login' | 'request' | 'set_password'>(() => {
    const params = new URLSearchParams(window.location.search);
    return params.get('setup_token') ? 'set_password' : 'login';
  });
  const [activeTab, setActiveTab] = useState<string>(() => getInitialActiveTab());
  const [setupToken, setSetupToken] = useState<string | null>(() => new URLSearchParams(window.location.search).get('setup_token'));
  const [chatHistory, setChatHistory] = useState<ChatHistoryItem[]>([]);
  const [generatorHistory, setGeneratorHistory] = useState<GeneratorHistoryItem[]>([]);
  const [activeChatSessionId, setActiveChatSessionId] = useState<string | null>(() => getInitialActiveChatSessionId());
  const [activeGeneratorHistoryId, setActiveGeneratorHistoryId] = useState<string | null>(null);
  const [chatOpenRequest, setChatOpenRequest] = useState<{ sessionId: string; nonce: number } | null>(() => {
    const initial = getInitialActiveChatSessionId();
    return initial ? { sessionId: initial, nonce: Date.now() } : null;
  });
  const [activeSettingsSection, setActiveSettingsSection] = useState<'details' | 'password'>('details');
  const [generatorOpenRequest, setGeneratorOpenRequest] = useState<{ id: string; nonce: number } | null>(null);
  const [chatNewSessionRequest, setChatNewSessionRequest] = useState<number | null>(null);
  const [generatorNewSessionRequest, setGeneratorNewSessionRequest] = useState<number | null>(null);

  useEffect(() => {
    if (!authToken) {
      setCurrentUser(null);
      setAuthLoading(false);
      return;
    }
    setAuthLoading(true);
    fetch(`${apiBase}/auth/me`, {
      headers: { Authorization: `Bearer ${authToken}` },
    })
      .then(async (res) => {
        if (!res.ok) throw new Error(`Session invalid (${res.status})`);
        return res.json();
      })
      .then((data) => {
        setCurrentUser(data.user as AuthUser);
      })
      .catch(() => {
        localStorage.removeItem('vidhi_auth_token');
        setAuthToken(null);
        setCurrentUser(null);
      })
      .finally(() => setAuthLoading(false));
  }, [authToken, apiBase]);

  useEffect(() => {
    if (currentUser?.role !== 'admin' && activeTab === 'admin') {
      setActiveTab('generator');
    }
  }, [currentUser, activeTab]);

  useEffect(() => {
    if (ALLOWED_TABS.has(activeTab)) {
      localStorage.setItem(ACTIVE_TAB_STORAGE_KEY, activeTab);
    }
  }, [activeTab]);

  useEffect(() => {
    try {
      if (activeChatSessionId) {
        sessionStorage.setItem(ACTIVE_CHAT_SESSION_STORAGE_KEY, activeChatSessionId);
      } else {
        sessionStorage.removeItem(ACTIVE_CHAT_SESSION_STORAGE_KEY);
      }
    } catch {
      // no-op if sessionStorage is unavailable
    }
  }, [activeChatSessionId]);

  const onLoginSuccess = (token: string, user: AuthUser) => {
    localStorage.setItem('vidhi_auth_token', token);
    setAuthToken(token);
    setCurrentUser(user);
    setActiveTab('generator');
    setActiveChatSessionId(null);
    setActiveGeneratorHistoryId(null);
    setAuthView('login');
  };

  const onLogout = async () => {
    try {
      if (authToken) {
        await fetch(`${apiBase}/auth/logout`, {
          method: 'POST',
          headers: { Authorization: `Bearer ${authToken}` },
        });
      }
    } catch {
      // ignore logout request failures and clear local session anyway
    }
    localStorage.removeItem('vidhi_auth_token');
    setAuthToken(null);
    setCurrentUser(null);
    setActiveTab('generator');
    setChatHistory([]);
    setGeneratorHistory([]);
    setActiveChatSessionId(null);
    setActiveGeneratorHistoryId(null);
    setChatOpenRequest(null);
    setGeneratorOpenRequest(null);
    setChatNewSessionRequest(null);
    setGeneratorNewSessionRequest(null);
    setAuthView('login');
  };

  const goToLogin = () => {
    setAuthView('login');
    setSetupToken(null);
    const url = new URL(window.location.href);
    url.searchParams.delete('setup_token');
    window.history.replaceState({}, '', url.toString());
  };

  const openChatHistoryItem = (sessionId: string) => {
    if (!sessionId) return;
    setActiveTab('chat');
    setActiveChatSessionId(sessionId);
    setChatOpenRequest({ sessionId, nonce: Date.now() });
  };

  const startNewSession = () => {
    if (activeTab === 'generator') {
      setActiveGeneratorHistoryId(null);
      setGeneratorOpenRequest(null);
      setGeneratorNewSessionRequest(Date.now());
      return;
    }
    if (activeTab === 'chat') {
      setActiveChatSessionId(null);
      setChatOpenRequest(null);
      setChatNewSessionRequest(Date.now());
      return;
    }
    // Fallback: start a new chat session when current module has no session concept.
    setActiveTab('chat');
    setActiveChatSessionId(null);
    setChatOpenRequest(null);
    setChatNewSessionRequest(Date.now());
  };

  const openGeneratorHistoryItem = (id: string) => {
    if (!id) return;
    setActiveTab('generator');
    setActiveGeneratorHistoryId(id);
    setGeneratorOpenRequest({ id, nonce: Date.now() });
  };

  const openSettingsSection = (section: 'details' | 'password') => {
    setActiveSettingsSection(section);
    setActiveTab('settings');
  };

  if (authLoading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-surface-container-low">
        <div className="flex items-center gap-3 text-on-surface-variant">
          <Loader2 size={20} className="animate-spin" />
          Checking session...
        </div>
      </div>
    );
  }

  if (!authToken || !currentUser) {
    if (authView === 'request') {
      return <RequestAccessPage apiBase={apiBase} onBackToLogin={goToLogin} />;
    }
    if (authView === 'set_password' && setupToken) {
      return <SetPasswordPage apiBase={apiBase} token={setupToken} onBackToLogin={goToLogin} />;
    }
    return (
      <LoginPage
        apiBase={apiBase}
        onLoginSuccess={onLoginSuccess}
        onShowRequestAccess={() => setAuthView('request')}
      />
    );
  }

  return (
    <div className="flex min-h-screen bg-surface font-body overflow-hidden">
      <Sidebar
        activeTab={activeTab}
        activeSettingsSection={activeSettingsSection}
        setActiveTab={setActiveTab}
        isAdmin={currentUser.role === 'admin'}
        onStartNewSession={startNewSession}
        chatHistory={chatHistory}
        generatorHistory={generatorHistory}
        activeChatSessionId={activeChatSessionId}
        activeGeneratorHistoryId={activeGeneratorHistoryId}
        onSelectChatHistory={openChatHistoryItem}
        onSelectGeneratorHistory={openGeneratorHistoryItem}
        onSelectSettingsSection={openSettingsSection}
      />
      
      <main className="flex-1 ml-64 flex flex-col h-screen relative">
        <Header currentUserName={currentUser.name} onLogout={onLogout} />
        
        <AnimatePresence mode="wait">
          {activeTab === 'analyzer' ? (
            <motion.div 
              key="analyzer"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              className="flex-1 flex flex-col overflow-hidden"
            >
              <DocumentAnalyzer />
            </motion.div>
          ) : activeTab === 'chat' ? (
            <motion.div 
              key="chat"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              className="flex-1 flex flex-col overflow-hidden"
            >
              <LegalChat
                authToken={authToken}
                openSessionRequest={chatOpenRequest}
                newSessionRequest={chatNewSessionRequest}
                onChatSessionsChange={setChatHistory}
                onActiveSessionChange={setActiveChatSessionId}
              />
            </motion.div>
          ) : activeTab === 'generator' ? (
            <motion.div 
              key="generator"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              className="flex-1 flex flex-col overflow-hidden"
            >
              <DocumentGenerator
                authToken={authToken}
                currentUserName={currentUser.name}
                currentUserEmail={currentUser.email}
                currentUserAdvocateAddress={currentUser.advocate_address}
                currentUserAdvocateMobile={currentUser.advocate_mobile}
                openHistoryRequest={generatorOpenRequest}
                newSessionRequest={generatorNewSessionRequest}
                onHistoryChange={setGeneratorHistory}
                onActiveHistoryChange={setActiveGeneratorHistoryId}
              />
            </motion.div>
          ) : activeTab === 'admin' && currentUser.role === 'admin' ? (
            <motion.div
              key="admin"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              className="flex-1 flex flex-col overflow-hidden"
            >
              <AdminAccessPage apiBase={apiBase} authToken={authToken} />
            </motion.div>
          ) : activeTab === 'predictor' ? (
            <motion.div 
              key="predictor"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              className="flex-1 flex flex-col overflow-hidden"
            >
              <WinPredictor />
            </motion.div>
          ) : activeTab === 'settings' ? (
            <motion.div
              key="settings"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              className="flex-1 flex flex-col overflow-hidden"
            >
              <SettingsPage
                authToken={authToken}
                currentUser={currentUser}
                onUserUpdated={setCurrentUser}
                activeSection={activeSettingsSection}
              />
            </motion.div>
          ) : (
            <motion.div 
              key="placeholder"
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -20 }}
              className="flex-1 flex items-center justify-center p-8"
            >
              <div className="text-center space-y-4 max-w-md">
                <div className="w-16 h-16 bg-surface-container rounded-full flex items-center justify-center mx-auto text-on-surface-variant">
                  <Search size={32} />
                </div>
                <h2 className="text-2xl font-headline font-bold text-primary">
                  {activeTab.charAt(0).toUpperCase() + activeTab.slice(1).replace(/([A-Z])/g, ' $1')} Module
                </h2>
                <p className="text-on-surface-variant">
                  This module is currently in development. Please use the Document Analyzer to review legal agreements.
                </p>
              </div>
            </motion.div>
          )}
        </AnimatePresence>
      </main>
    </div>
  );
}
