import React from 'react';
import { useMemo, useState } from 'react';
import {
  MessageSquare,
  FileText,
  BarChart3,
  TrendingUp,
  ShieldCheck,
  Plus,
  Library,
  Settings,
  Bell,
  LogOut,
  X,
} from 'lucide-react';

interface NavItem {
  id: string;
  label: string;
  icon: React.ElementType;
}

interface SidebarProps {
  activeTab: string;
  activeSettingsSection: 'details' | 'password';
  setActiveTab: (id: string) => void;
  isAdmin: boolean;
  onStartNewSession: () => void;
  chatHistory: Array<{
    session_id: string;
    title: string;
    last_message_at: string;
    message_count: number;
    preview?: string;
  }>;
  generatorHistory: Array<{
    id: string;
    title: string;
    created_at: string;
    preview?: string;
  }>;
  activeChatSessionId: string | null;
  activeGeneratorHistoryId: string | null;
  onSelectChatHistory: (sessionId: string) => void;
  onSelectGeneratorHistory: (itemId: string) => void;
  onSelectSettingsSection: (section: 'details' | 'password') => void;
}

interface HeaderProps {
  currentUserName: string;
  onLogout: () => void;
}

export const Sidebar = ({
  activeTab,
  activeSettingsSection,
  setActiveTab,
  isAdmin,
  onStartNewSession,
  chatHistory,
  generatorHistory,
  activeChatSessionId,
  activeGeneratorHistoryId,
  onSelectChatHistory,
  onSelectGeneratorHistory,
  onSelectSettingsSection,
}: SidebarProps) => {
  const [isLibraryOpen, setIsLibraryOpen] = useState(false);
  const [isSettingsOpen, setIsSettingsOpen] = useState(false);

  const moduleItems: NavItem[] = useMemo(() => {
    const items: NavItem[] = [
      { id: 'chat', label: 'AI Legal Chat', icon: MessageSquare },
      { id: 'generator', label: 'Document Generator', icon: FileText },
      { id: 'analyzer', label: 'Document Analyzer', icon: BarChart3 },
      { id: 'predictor', label: 'Win Predictor', icon: TrendingUp },
    ];
    if (isAdmin) {
      items.push({ id: 'admin', label: 'Admin Access', icon: ShieldCheck });
    }
    return items;
  }, [isAdmin]);

  const activeModule = moduleItems.find((item) => item.id === activeTab);

  const selectModule = (id: string) => {
    setActiveTab(id);
    setIsLibraryOpen(false);
    setIsSettingsOpen(false);
  };

  const openLibrary = () => {
    setIsSettingsOpen(false);
    setIsLibraryOpen(true);
  };

  const openSettings = () => {
    setIsLibraryOpen(false);
    setIsSettingsOpen(true);
  };

  const selectSettingsSection = (section: 'details' | 'password') => {
    onSelectSettingsSection(section);
    setIsSettingsOpen(false);
  };

  const formatHistoryTime = (iso: string) => {
    if (!iso) return '';
    const parsed = new Date(iso);
    if (Number.isNaN(parsed.getTime())) return '';
    return parsed.toLocaleDateString(undefined, {
      month: 'short',
      day: 'numeric',
    });
  };

  const showChatHistory = activeTab === 'chat';
  const showGeneratorHistory = activeTab === 'generator';

  return (
    <>
      <aside className="fixed left-0 top-0 z-50 flex h-full w-64 flex-col border-r border-outline-variant/15 bg-surface-container-low p-4">
        <div className="mb-6 px-2 py-4">
          <h1 className="text-xl font-headline font-bold text-primary">The Digital Atelier</h1>
          <p className="font-label text-[10px] font-bold uppercase tracking-[0.2em] text-on-surface-variant">Legal AI Systems</p>
        </div>

        <div className="flex min-h-0 flex-1 flex-col">
          <div className="space-y-2 rounded-xl border border-outline-variant/25 bg-surface-container p-4">
            <p className="text-[10px] font-bold uppercase tracking-[0.18em] text-on-surface-variant">Active Workspace</p>
            <div className="flex items-center gap-3 text-on-surface">
              {activeModule ? <activeModule.icon size={18} /> : <Library size={18} />}
              <span className="text-sm font-semibold">{activeModule?.label ?? 'Select from Library'}</span>
            </div>
          </div>

          {(showChatHistory || showGeneratorHistory) && (
            <div className="mt-4 flex min-h-0 flex-1 flex-col overflow-hidden rounded-xl border border-outline-variant/25 bg-surface-container-high/50 p-3">
              <div className="mb-2 flex items-center justify-between">
                <p className="text-[10px] font-bold uppercase tracking-[0.14em] text-on-surface-variant">
                  {showChatHistory ? 'Chat History' : 'Generator History'}
                </p>
                <span className="text-[10px] text-on-surface-variant/80">
                  {showChatHistory ? chatHistory.length : generatorHistory.length}
                </span>
              </div>

              <div className="max-h-[32vh] space-y-1 overflow-y-auto pr-1">
                {showChatHistory &&
                  chatHistory.map((item) => (
                    <button
                      key={item.session_id}
                      onClick={() => onSelectChatHistory(item.session_id)}
                      className={`w-full rounded-lg border px-2.5 py-2 text-left transition-colors ${
                        activeChatSessionId === item.session_id
                          ? 'border-primary/35 bg-primary/10 text-primary'
                          : 'border-transparent text-on-surface-variant hover:border-outline-variant/30 hover:bg-surface-container-high/40 hover:text-on-surface'
                      }`}
                    >
                      <div className="truncate text-xs font-semibold">{item.title || 'Untitled Chat'}</div>
                      <div className="mt-0.5 truncate text-[10px] text-on-surface-variant/80">
                        {item.preview || `${item.message_count} messages`}
                      </div>
                      <div className="mt-1 text-[9px] text-on-surface-variant/70">{formatHistoryTime(item.last_message_at)}</div>
                    </button>
                  ))}

                {showGeneratorHistory &&
                  generatorHistory.map((item) => (
                    <button
                      key={item.id}
                      onClick={() => onSelectGeneratorHistory(item.id)}
                      className={`w-full rounded-lg border px-2.5 py-2 text-left transition-colors ${
                        activeGeneratorHistoryId === item.id
                          ? 'border-primary/35 bg-primary/10 text-primary'
                          : 'border-transparent text-on-surface-variant hover:border-outline-variant/30 hover:bg-surface-container-high/40 hover:text-on-surface'
                      }`}
                    >
                      <div className="truncate text-xs font-semibold">{item.title || 'Generated Notice'}</div>
                      <div className="mt-0.5 truncate text-[10px] text-on-surface-variant/80">
                        {item.preview || 'Open saved draft'}
                      </div>
                      <div className="mt-1 text-[9px] text-on-surface-variant/70">{formatHistoryTime(item.created_at)}</div>
                    </button>
                  ))}

                {showChatHistory && chatHistory.length === 0 && (
                  <p className="px-2 py-3 text-[11px] text-on-surface-variant">No chat sessions yet.</p>
                )}
                {showGeneratorHistory && generatorHistory.length === 0 && (
                  <p className="px-2 py-3 text-[11px] text-on-surface-variant">No generated notices yet.</p>
                )}
              </div>
            </div>
          )}
        </div>

        <div className="border-t border-outline-variant/20 pt-4">
          <button
            onClick={onStartNewSession}
            className="mb-3 flex w-full items-center justify-center space-x-2 rounded-xl bg-gradient-to-r from-primary to-primary-container px-4 py-3 text-sm font-semibold text-on-primary shadow-lg shadow-black/30 transition-opacity hover:opacity-90"
          >
            <Plus size={18} />
            <span>New Session</span>
          </button>
          <div className="mb-6" />

          <div className="space-y-1">
            <button
              onClick={openLibrary}
              className={`flex w-full items-center space-x-3 rounded-lg px-4 py-3 transition-all ${
                isLibraryOpen
                  ? 'bg-surface-container-highest text-primary font-semibold'
                  : 'text-on-surface-variant hover:bg-surface-container-high/50 hover:text-primary'
              }`}
            >
              <Library size={20} />
              <span className="text-sm">Library</span>
            </button>
            <button
              onClick={openSettings}
              className={`flex w-full items-center space-x-3 rounded-lg px-4 py-3 transition-all ${
                isSettingsOpen || activeTab === 'settings'
                  ? 'bg-surface-container-highest text-primary font-semibold'
                  : 'text-on-surface-variant hover:bg-surface-container-high/50 hover:text-primary'
              }`}
            >
              <Settings size={20} />
              <span className="text-sm">Settings</span>
            </button>
          </div>
        </div>
      </aside>

      {isLibraryOpen && (
        <>
          <button
            aria-label="Close library picker"
            onClick={() => setIsLibraryOpen(false)}
            className="fixed inset-0 z-[60] bg-surface/50 backdrop-blur-sm"
          />
          <div className="fixed left-[17.5rem] top-1/2 z-[70] max-h-[70vh] w-[22rem] -translate-y-1/2 overflow-y-auto rounded-2xl border border-outline-variant/30 bg-surface-container-lowest p-4 shadow-2xl shadow-black/60">
            <div className="mb-4 flex items-center justify-between">
              <div>
                <h3 className="text-base font-bold text-primary">Library</h3>
                <p className="text-xs text-on-surface-variant">Choose a workspace module</p>
              </div>
              <button
                onClick={() => setIsLibraryOpen(false)}
                className="rounded-lg p-2 text-on-surface-variant transition-colors hover:bg-surface-container-high/40 hover:text-primary"
              >
                <X size={16} />
              </button>
            </div>

            <div className="space-y-2">
              {moduleItems.map((item) => (
                <button
                  key={item.id}
                  onClick={() => selectModule(item.id)}
                  className={`flex w-full items-center space-x-3 rounded-lg px-4 py-3 transition-all ${
                    activeTab === item.id
                      ? 'bg-surface-container-highest text-primary font-semibold'
                      : 'text-on-surface-variant hover:bg-surface-container-high/40 hover:text-primary'
                  }`}
                >
                  <item.icon size={18} />
                  <span className="text-sm">{item.label}</span>
                </button>
              ))}
            </div>
          </div>
        </>
      )}

      {isSettingsOpen && (
        <>
          <button
            aria-label="Close settings picker"
            onClick={() => setIsSettingsOpen(false)}
            className="fixed inset-0 z-[60] bg-surface/50 backdrop-blur-sm"
          />
          <div className="fixed left-[17.5rem] top-1/2 z-[70] max-h-[70vh] w-[22rem] -translate-y-1/2 overflow-y-auto rounded-2xl border border-outline-variant/30 bg-surface-container-lowest p-4 shadow-2xl shadow-black/60">
            <div className="mb-4 flex items-center justify-between">
              <div>
                <h3 className="text-base font-bold text-primary">Settings</h3>
                <p className="text-xs text-on-surface-variant">Choose a settings section</p>
              </div>
              <button
                onClick={() => setIsSettingsOpen(false)}
                className="rounded-lg p-2 text-on-surface-variant transition-colors hover:bg-surface-container-high/40 hover:text-primary"
              >
                <X size={16} />
              </button>
            </div>

            <div className="space-y-2">
              <button
                onClick={() => selectSettingsSection('details')}
                className={`flex w-full items-center space-x-3 rounded-lg px-4 py-3 transition-all ${
                  activeTab === 'settings' && activeSettingsSection === 'details'
                    ? 'bg-surface-container-highest text-primary font-semibold'
                    : 'text-on-surface-variant hover:bg-surface-container-high/40 hover:text-primary'
                }`}
              >
                <Settings size={18} />
                <span className="text-sm">Details</span>
              </button>
              <button
                onClick={() => selectSettingsSection('password')}
                className={`flex w-full items-center space-x-3 rounded-lg px-4 py-3 transition-all ${
                  activeTab === 'settings' && activeSettingsSection === 'password'
                    ? 'bg-surface-container-highest text-primary font-semibold'
                    : 'text-on-surface-variant hover:bg-surface-container-high/40 hover:text-primary'
                }`}
              >
                <Settings size={18} />
                <span className="text-sm">Reset Password</span>
              </button>
            </div>
          </div>
        </>
      )}
    </>
  );
};

export const Header = ({ currentUserName, onLogout }: HeaderProps) => (
  <header className="glass-panel sticky top-0 z-40 flex w-full items-center justify-between border-b border-outline-variant/15 px-8 py-4 shadow-2xl shadow-black/30">
    <div className="flex items-center">
      <span className="text-2xl font-headline italic text-primary">Vidhi AI</span>
    </div>

    <div className="flex items-center space-x-8">
      <nav className="flex items-center space-x-6">
        <a href="#" className="text-sm text-on-surface-variant transition-colors hover:text-primary">
          Explorer
        </a>
        <a href="#" className="border-b-2 border-primary pb-1 text-sm font-bold text-primary">
          Workspace
        </a>
      </nav>

      <div className="flex items-center space-x-4">
        <button className="rounded-full p-2 text-on-surface-variant transition-colors hover:bg-surface-container-high/60 hover:text-primary">
          <Bell size={20} />
        </button>
        <button
          onClick={onLogout}
          className="inline-flex items-center gap-2 rounded-lg border border-outline-variant/30 px-3 py-1.5 text-xs font-semibold text-on-surface-variant hover:border-primary/30 hover:text-primary"
        >
          <LogOut size={14} />
          Logout
        </button>
        <span className="hidden text-xs font-semibold text-on-surface-variant md:block">{currentUserName}</span>
        <div className="w-8 h-8 overflow-hidden rounded-full border border-primary/30 ring-2 ring-primary/10">
          <img
            src="https://picsum.photos/seed/lawyer/100/100"
            alt="User Profile"
            className="h-full w-full object-cover"
            referrerPolicy="no-referrer"
          />
        </div>
      </div>
    </div>
  </header>
);
