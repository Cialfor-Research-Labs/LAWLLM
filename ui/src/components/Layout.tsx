import React, { useEffect, useMemo, useRef, useState } from 'react';
import {
  Library as LibraryIcon,
  ChevronDown,
  MessageSquare,
  FileText,
  BarChart3,
  TrendingUp,
  ShieldCheck,
  Gavel,
  Plus,
  Settings,
  KeyRound,
  Bell,
  LogOut,
  Moon,
  Sun,
} from 'lucide-react';

export type ThemeMode = 'light' | 'dark';

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
  onOpenProfile: () => void;
  themeMode: ThemeMode;
  onToggleTheme: () => void;
}

interface ThemeToggleProps {
  themeMode: ThemeMode;
  onToggleTheme: () => void;
  compact?: boolean;
}

export const ThemeToggle = ({ themeMode, onToggleTheme, compact = false }: ThemeToggleProps) => {
  const isLight = themeMode === 'light';
  const Icon = isLight ? Moon : Sun;
  const label = isLight ? 'Dark Mode' : 'Light Mode';

  return (
    <button
      type="button"
      onClick={onToggleTheme}
      className={`inline-flex items-center rounded-xl border border-outline-variant/30 bg-surface-container-low text-on-surface transition hover:border-primary/30 hover:text-primary ${
        compact ? 'gap-2 px-3 py-2 text-xs font-semibold' : 'gap-2.5 px-4 py-2.5 text-sm font-semibold'
      }`}
      aria-label={`Switch to ${label}`}
      title={`Switch to ${label}`}
    >
      <Icon size={compact ? 14 : 16} />
      <span className={compact ? 'hidden sm:inline' : ''}>{label}</span>
    </button>
  );
};

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
  const [isLibraryMenuOpen, setIsLibraryMenuOpen] = useState(false);
  const libraryMenuRef = useRef<HTMLDivElement | null>(null);

  const libraryOptions: NavItem[] = [
    { id: 'chat', label: 'AI Legal Chat', icon: MessageSquare },
    { id: 'generator', label: 'Legal Notice Generator', icon: FileText },
    { id: 'analyzer', label: 'Document Analyzer', icon: BarChart3 },
    { id: 'predictor', label: 'Win Predictor', icon: TrendingUp },
  ];
  const popupLibraryOptions = libraryOptions.filter(
    (option) => option.id !== 'analyzer' && option.id !== 'predictor'
  );

  const moduleItems: NavItem[] = useMemo(() => {
    const items: NavItem[] = [
      { id: 'library', label: 'Library', icon: LibraryIcon },
    ];
    if (isAdmin) {
      items.push({ id: 'admin', label: 'Admin Access', icon: ShieldCheck });
    }
    return items;
  }, [isAdmin]);

  const activeModuleByTab: Record<string, NavItem> = {
    library: { id: 'library', label: 'Library', icon: LibraryIcon },
    chat: { id: 'chat', label: 'AI Legal Chat', icon: MessageSquare },
    generator: { id: 'generator', label: 'Legal Notice Generator', icon: FileText },
    analyzer: { id: 'analyzer', label: 'Document Analyzer', icon: BarChart3 },
    predictor: { id: 'predictor', label: 'Win Predictor', icon: TrendingUp },
    admin: { id: 'admin', label: 'Admin Access', icon: ShieldCheck },
  };

  const activeModule =
    moduleItems.find((item) => item.id === activeTab) ||
    activeModuleByTab[activeTab];

  const selectModule = (id: string) => {
    setActiveTab(id);
    if (id !== 'library') {
      setIsLibraryMenuOpen(false);
    }
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

  useEffect(() => {
    if (!isLibraryMenuOpen) return;
    const handleClickOutside = (event: MouseEvent) => {
      const target = event.target as Node;
      if (libraryMenuRef.current && !libraryMenuRef.current.contains(target)) {
        setIsLibraryMenuOpen(false);
      }
    };
    document.addEventListener('mousedown', handleClickOutside);
    return () => {
      document.removeEventListener('mousedown', handleClickOutside);
    };
  }, [isLibraryMenuOpen]);

  return (
    <>
      <aside className="fixed left-0 top-0 z-50 flex h-screen w-64 shrink-0 flex-col border-r border-[color:var(--app-sidebar-border)] bg-[var(--app-sidebar-bg)]">
        <div className="p-6">
          <div className="mb-8 flex items-center gap-3">
            <div className="flex h-10 w-10 items-center justify-center rounded-lg bg-primary-container shadow-lg">
              <Gavel className="h-6 w-6 text-on-primary-container" />
            </div>
            <div>
              <h1 className="text-xl leading-none font-headline italic text-[var(--app-sidebar-brand)]">Legal AI</h1>
              <p className="mt-1 font-label text-[10px] uppercase tracking-widest text-[var(--app-sidebar-muted)]">Jurisprudential Engine</p>
            </div>
          </div>

          <button
            className="mb-8 flex w-full items-center justify-center gap-2 rounded-lg bg-gradient-to-r from-primary to-primary-container py-3 font-label text-xs font-bold uppercase tracking-widest text-on-primary shadow-ambient transition-all hover:brightness-110 active:scale-95"
            onClick={onStartNewSession}
          >
            <Plus className="h-4 w-4" />
            New Session
          </button>

          <nav className="space-y-1">
            {moduleItems.map((item) => (
              item.id === 'library' ? (
                <div key={item.id} ref={libraryMenuRef} className="relative">
                  <button
                    onClick={() => {
                      setIsLibraryMenuOpen((prev) => !prev);
                    }}
                    className={`group relative flex w-full items-center gap-4 px-6 py-3 transition-all ${
                      activeTab === 'library' || libraryOptions.some((opt) => opt.id === activeTab)
                        ? 'border-l-4 border-primary bg-[var(--app-sidebar-active-bg)] text-[var(--app-sidebar-active-text)]'
                        : 'text-[var(--app-sidebar-muted)] hover:bg-[var(--app-sidebar-hover-bg)] hover:text-[var(--app-sidebar-fg)]'
                    }`}
                  >
                    <item.icon className="h-5 w-5" />
                    <span className="font-label text-xs uppercase tracking-widest">{item.label}</span>
                    <ChevronDown
                      className={`ml-auto h-4 w-4 transition-transform ${isLibraryMenuOpen ? 'rotate-180' : ''}`}
                    />
                  </button>

                  {isLibraryMenuOpen && (
                    <div className="absolute left-full top-0 z-50 ml-2 w-80 rounded-xl border border-outline-variant/25 bg-surface-container-lowest p-2 shadow-2xl">
                      <div className="mb-2 px-2 pt-1">
                        <p className="text-[10px] font-bold uppercase tracking-[0.14em] text-on-surface-variant">Library</p>
                      </div>

                      <div className="space-y-1 pb-2">
                        {popupLibraryOptions.map((option) => (
                          <button
                            key={option.id}
                            onClick={() => {
                              setActiveTab(option.id);
                              setIsLibraryMenuOpen(false);
                            }}
                            className={`flex w-full items-center gap-3 rounded-lg px-3 py-2.5 text-left text-xs font-semibold uppercase tracking-wide transition-colors ${
                              activeTab === option.id
                                ? 'bg-primary/15 text-primary'
                                : 'text-on-surface-variant hover:bg-surface-container-high/40 hover:text-on-surface'
                            }`}
                          >
                            <option.icon className="h-4 w-4" />
                            <span>{option.label}</span>
                          </button>
                        ))}
                      </div>

                    </div>
                  )}
                </div>
              ) : (
                <button
                  key={item.id}
                  onClick={() => selectModule(item.id)}
                  className={`group relative flex w-full items-center gap-4 px-6 py-3 transition-all ${
                    activeTab === item.id
                      ? 'border-l-4 border-primary bg-[var(--app-sidebar-active-bg)] text-[var(--app-sidebar-active-text)]'
                      : 'text-[var(--app-sidebar-muted)] hover:bg-[var(--app-sidebar-hover-bg)] hover:text-[var(--app-sidebar-fg)]'
                  }`}
                >
                  <item.icon
                    className={`h-5 w-5 transition-transform duration-500 ${
                      activeTab !== item.id ? 'group-hover:rotate-12' : ''
                    }`}
                  />
                  <span className="font-label text-xs uppercase tracking-widest">{item.label}</span>
                </button>
              )
            ))}
          </nav>
        </div>

        <div className="flex min-h-0 flex-1 flex-col px-6 pb-6">
          {activeModule && (
            <div className="mb-4 rounded-2xl border border-[color:var(--app-sidebar-panel-border)] bg-[var(--app-sidebar-panel-bg)] p-4 shadow-[0_10px_24px_rgba(14,18,42,0.08)] backdrop-blur-md">
              <p className="mb-2 text-[10px] font-bold uppercase tracking-[0.18em] text-[var(--app-sidebar-panel-muted)]">Active Workspace</p>
              <div className="flex items-center gap-2 text-sm font-semibold text-[var(--app-sidebar-panel-text)]">
                <activeModule.icon size={16} />
                <span>{activeModule.label}</span>
              </div>
            </div>
          )}

          {activeTab === 'chat' ? (
            <div className="flex min-h-0 flex-1 flex-col overflow-hidden rounded-2xl border border-[color:var(--app-sidebar-panel-border)] bg-[var(--app-sidebar-panel-bg)] p-4 shadow-[0_10px_24px_rgba(14,18,42,0.08)] backdrop-blur-md">
              <div className="mb-2 flex items-center justify-between">
                <p className="text-[10px] font-bold uppercase tracking-[0.14em] text-[var(--app-sidebar-panel-muted)]">Chat History</p>
                <span className="text-[10px] text-[var(--app-sidebar-panel-muted)]">{chatHistory.length}</span>
              </div>
              <div className="space-y-2 overflow-y-auto pr-1 no-scrollbar">
                {chatHistory.map((item) => (
                  <button
                    key={item.session_id}
                    onClick={() => onSelectChatHistory(item.session_id)}
                    className={`w-full rounded-xl border px-3 py-3 text-left transition-colors ${
                      activeChatSessionId === item.session_id
                        ? 'border-[color:var(--app-sidebar-panel-active-border)] bg-[var(--app-sidebar-panel-active-bg)] text-[var(--app-sidebar-panel-active-text)]'
                        : 'border-transparent text-[var(--app-sidebar-panel-text)] hover:border-[color:var(--app-sidebar-panel-border)] hover:bg-[var(--app-sidebar-panel-hover-bg)]'
                    }`}
                  >
                    <div className="truncate text-xs font-semibold">{item.title || 'Untitled Chat'}</div>
                    <div className="mt-1 truncate text-[10px] text-[var(--app-sidebar-panel-muted)]">
                      {item.preview || `${item.message_count} messages`}
                    </div>
                    <div className="mt-2 text-[9px] font-medium text-[var(--app-sidebar-panel-muted)]">{formatHistoryTime(item.last_message_at)}</div>
                  </button>
                ))}
                {chatHistory.length === 0 && (
                  <p className="px-2 py-2 text-[11px] text-[var(--app-sidebar-panel-muted)]">No chat sessions yet.</p>
                )}
              </div>
            </div>
          ) : activeTab === 'generator' ? (
            <div className="flex min-h-0 flex-1 flex-col overflow-hidden rounded-2xl border border-[color:var(--app-sidebar-panel-border)] bg-[var(--app-sidebar-panel-bg)] p-4 shadow-[0_10px_24px_rgba(14,18,42,0.08)] backdrop-blur-md">
              <div className="mb-2 flex items-center justify-between">
                <p className="text-[10px] font-bold uppercase tracking-[0.14em] text-[var(--app-sidebar-panel-muted)]">Document History</p>
                <span className="text-[10px] text-[var(--app-sidebar-panel-muted)]">{generatorHistory.length}</span>
              </div>
              <div className="space-y-2 overflow-y-auto pr-1 no-scrollbar">
                {generatorHistory.map((item) => (
                  <button
                    key={item.id}
                    onClick={() => onSelectGeneratorHistory(item.id)}
                    className={`w-full rounded-xl border px-3 py-3 text-left transition-colors ${
                      activeGeneratorHistoryId === item.id
                        ? 'border-[color:var(--app-sidebar-panel-active-border)] bg-[var(--app-sidebar-panel-active-bg)] text-[var(--app-sidebar-panel-active-text)]'
                        : 'border-transparent text-[var(--app-sidebar-panel-text)] hover:border-[color:var(--app-sidebar-panel-border)] hover:bg-[var(--app-sidebar-panel-hover-bg)]'
                    }`}
                  >
                    <div className="truncate text-xs font-semibold">{item.title || 'Generated Notice'}</div>
                    <div className="mt-1 truncate text-[10px] text-[var(--app-sidebar-panel-muted)]">
                      {item.preview || 'Open saved draft'}
                    </div>
                    <div className="mt-2 text-[9px] font-medium text-[var(--app-sidebar-panel-muted)]">{formatHistoryTime(item.created_at)}</div>
                  </button>
                ))}
                {generatorHistory.length === 0 && (
                  <p className="px-2 py-2 text-[11px] text-[var(--app-sidebar-panel-muted)]">No generated notices yet.</p>
                )}
              </div>
            </div>
          ) : (
            <div className="flex-1" />
          )}
        </div>

        <div className="mt-auto space-y-1 border-t border-[color:var(--app-sidebar-border)] p-6">
          <button
            onClick={() => onSelectSettingsSection('details')}
            className={`group flex w-full items-center gap-4 px-6 py-3 transition-all ${
              activeTab === 'settings' && activeSettingsSection === 'details'
                ? 'border-l-4 border-primary bg-[var(--app-sidebar-active-bg)] text-[var(--app-sidebar-active-text)]'
                : 'text-[var(--app-sidebar-muted)] hover:bg-[var(--app-sidebar-hover-bg)] hover:text-[var(--app-sidebar-fg)]'
            }`}
          >
            <Settings
              className={`h-5 w-5 transition-transform duration-500 ${
                !(activeTab === 'settings' && activeSettingsSection === 'details') ? 'group-hover:rotate-12' : ''
              }`}
            />
            <span className="font-label text-xs uppercase tracking-widest">Settings</span>
          </button>
          <button
            onClick={() => onSelectSettingsSection('password')}
            className={`group flex w-full items-center gap-4 px-6 py-3 transition-all ${
              activeTab === 'settings' && activeSettingsSection === 'password'
                ? 'border-l-4 border-primary bg-[var(--app-sidebar-active-bg)] text-[var(--app-sidebar-active-text)]'
                : 'text-[var(--app-sidebar-muted)] hover:bg-[var(--app-sidebar-hover-bg)] hover:text-[var(--app-sidebar-fg)]'
            }`}
          >
            <KeyRound
              className={`h-5 w-5 transition-transform duration-500 ${
                !(activeTab === 'settings' && activeSettingsSection === 'password') ? 'group-hover:rotate-12' : ''
              }`}
            />
            <span className="font-label text-[11px] uppercase tracking-[0.12em] whitespace-nowrap">Reset Password</span>
          </button>
        </div>
      </aside>
    </>
  );
};

export const Header = ({ currentUserName, onLogout, onOpenProfile, themeMode, onToggleTheme }: HeaderProps) => {
  const [isProfileMenuOpen, setIsProfileMenuOpen] = useState(false);
  const profileMenuRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (!isProfileMenuOpen) return;
    const handleClickOutside = (event: MouseEvent) => {
      const target = event.target as Node;
      if (profileMenuRef.current && !profileMenuRef.current.contains(target)) {
        setIsProfileMenuOpen(false);
      }
    };
    document.addEventListener('mousedown', handleClickOutside);
    return () => {
      document.removeEventListener('mousedown', handleClickOutside);
    };
  }, [isProfileMenuOpen]);

  return (
    <header className="glass-panel sticky top-0 z-40 flex w-full items-center justify-between border-b border-outline-variant/15 px-8 py-4 shadow-ambient">
      <div className="flex items-center">
        <span className="text-2xl font-headline italic text-primary">Legal AI</span>
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
          <ThemeToggle themeMode={themeMode} onToggleTheme={onToggleTheme} compact />
          <button className="rounded-full p-2 text-on-surface-variant transition-colors hover:bg-surface-container-high/60 hover:text-primary">
            <Bell size={20} />
          </button>
          <div className="relative" ref={profileMenuRef}>
            <div className="flex items-center gap-2">
              <button
                type="button"
                onClick={onOpenProfile}
                className="inline-flex items-center gap-3 rounded-full border border-outline-variant/30 bg-surface-container-low px-2 py-1.5 text-on-surface-variant transition hover:border-primary/30 hover:text-primary"
              >
                <span className="hidden text-xs font-semibold md:block">{currentUserName}</span>
                <div className="h-8 w-8 overflow-hidden rounded-full border border-primary/30 ring-2 ring-primary/10">
                  <img
                    src="https://picsum.photos/seed/lawyer/100/100"
                    alt="User Profile"
                    className="h-full w-full object-cover"
                    referrerPolicy="no-referrer"
                  />
                </div>
              </button>
              <button
                type="button"
                aria-label="Open profile menu"
                onClick={() => setIsProfileMenuOpen((prev) => !prev)}
                className="inline-flex h-10 w-10 items-center justify-center rounded-full border border-outline-variant/30 bg-surface-container-low text-on-surface-variant transition hover:border-primary/30 hover:text-primary"
              >
                <ChevronDown size={14} className={`transition-transform ${isProfileMenuOpen ? 'rotate-180' : ''}`} />
              </button>
            </div>

            {isProfileMenuOpen && (
              <div className="absolute right-0 top-[calc(100%+0.6rem)] z-50 w-56 overflow-hidden rounded-2xl border border-outline-variant/20 bg-surface-container-lowest shadow-xl">
                <div className="border-b border-outline-variant/10 px-4 py-3">
                  <div className="text-xs uppercase tracking-[0.12em] text-on-surface-variant">Signed in as</div>
                  <div className="mt-1 text-sm font-semibold text-on-surface">{currentUserName}</div>
                </div>
                <button
                  type="button"
                  onClick={() => {
                    setIsProfileMenuOpen(false);
                    onLogout();
                  }}
                  className="flex w-full items-center gap-3 px-4 py-3 text-sm font-semibold text-on-surface-variant transition hover:bg-surface-container-low hover:text-primary"
                >
                  <LogOut size={16} />
                  Logout
                </button>
              </div>
            )}
          </div>
        </div>
      </div>
    </header>
  );
};
