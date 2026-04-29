import React, { useEffect, useMemo, useRef, useState } from 'react';
import {
  Library as LibraryIcon,
  ChevronDown,
  MessageSquare,
  FileText,
  BarChart3,
  TrendingUp,
  ShieldCheck,
  Plus,
  Settings,
  KeyRound,
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

function formatHistoryTime(iso: string) {
  if (!iso) return '';
  const parsed = new Date(iso);
  if (Number.isNaN(parsed.getTime())) return '';
  return parsed.toLocaleDateString(undefined, {
    month: 'short',
    day: 'numeric',
  });
}

function getHistoryAccent(text: string) {
  const value = text.toLowerCase();
  if (/salary|employment|harassment|termination|workplace|wage/.test(value)) {
    return 'bg-orange-400';
  }
  if (/property|landlord|tenant|builder|rent|eviction|title|ownership/.test(value)) {
    return 'bg-sky-500';
  }
  if (/consumer|refund|service|warranty|product|complaint/.test(value)) {
    return 'bg-violet-500';
  }
  if (/contract|agreement|breach|money|recovery|cheque|maintenance/.test(value)) {
    return 'bg-emerald-500';
  }
  return 'bg-primary';
}

function getInitials(name: string) {
  const parts = name
    .split(/\s+/)
    .map((part) => part.trim())
    .filter(Boolean)
    .slice(0, 2);

  if (parts.length === 0) {
    return 'LA';
  }

  return parts.map((part) => part[0]?.toUpperCase() || '').join('');
}

export const ThemeToggle = ({ themeMode, onToggleTheme, compact = false }: ThemeToggleProps) => {
  const isLight = themeMode === 'light';
  const Icon = isLight ? Moon : Sun;
  const label = isLight ? 'Dark mode' : 'Light mode';

  return (
    <button
      type="button"
      onClick={onToggleTheme}
      className={`neutral-button ${compact ? 'px-3 py-2 text-xs' : ''}`}
      aria-label={`Switch to ${label}`}
      title={`Switch to ${label}`}
    >
      <Icon size={compact ? 14 : 16} />
      <span className={compact ? 'hidden sm:inline' : ''}>{label}</span>
    </button>
  );
};

function DesktopNavButton({
  icon: Icon,
  label,
  active,
  onClick,
  trailing,
  compact = false,
}: {
  icon: React.ElementType;
  label: string;
  active: boolean;
  onClick: () => void;
  trailing?: React.ReactNode;
  compact?: boolean;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`group flex w-full items-center gap-3 rounded-2xl px-4 py-3 text-left transition ${
        active
          ? 'bg-[var(--app-sidebar-active-bg)] text-[var(--app-sidebar-active-text)]'
          : 'text-[var(--app-sidebar-muted)] hover:bg-[var(--app-sidebar-hover-bg)] hover:text-[var(--app-sidebar-fg)]'
      }`}
    >
      <span className={`h-2.5 w-2.5 shrink-0 rounded-full ${active ? 'bg-primary' : 'bg-outline'}`} />
      <Icon className="h-4 w-4 shrink-0" />
      <span className={`${compact ? 'text-xs' : 'text-sm'} font-medium`}>{label}</span>
      {trailing ? <span className="ml-auto">{trailing}</span> : null}
    </button>
  );
}

function HistoryPanel({
  heading,
  count,
  items,
  activeId,
  emptyLabel,
  onSelect,
  dateField,
}: {
  heading: string;
  count: number;
  items: Array<Record<string, string | number | undefined>>;
  activeId: string | null;
  emptyLabel: string;
  onSelect: (id: string) => void;
  dateField: 'last_message_at' | 'created_at';
}) {
  return (
    <div className="app-shell-panel flex min-h-0 flex-1 flex-col overflow-hidden bg-[var(--app-sidebar-panel-bg)]">
      <div className="flex items-center justify-between border-b border-[color:var(--app-sidebar-panel-border)] px-4 py-3">
        <div>
          <p className="text-[11px] font-semibold text-[var(--app-sidebar-panel-text)]">{heading}</p>
          <p className="mt-0.5 text-[11px] text-[var(--app-sidebar-panel-muted)]">
            Recent work
          </p>
        </div>
        <span className="status-pill bg-transparent text-[var(--app-sidebar-panel-muted)]">{count}</span>
      </div>

      <div className="min-h-0 flex-1 space-y-2 overflow-y-auto p-3 no-scrollbar">
        {items.map((item) => {
          const id = String(item.session_id || item.id || '');
          const title = String(item.title || '');
          const preview = String(item.preview || (item.message_count ? `${item.message_count} messages` : ''));
          const isActive = activeId === id;

          return (
            <button
              key={id}
              type="button"
              onClick={() => onSelect(id)}
              className={`w-full rounded-2xl border px-3 py-3 text-left transition ${
                isActive
                  ? 'border-[color:var(--app-sidebar-panel-active-border)] bg-[var(--app-sidebar-panel-active-bg)] text-[var(--app-sidebar-panel-active-text)]'
                  : 'border-transparent text-[var(--app-sidebar-panel-text)] hover:border-[color:var(--app-sidebar-panel-border)] hover:bg-[var(--app-sidebar-panel-hover-bg)]'
              }`}
            >
              <div className="flex items-start gap-2">
                <span className={`mt-1 h-2.5 w-2.5 shrink-0 rounded-full ${getHistoryAccent(title || preview)}`} />
                <div className="min-w-0 flex-1">
                  <div className="two-line-clamp text-sm font-medium leading-5">
                    {title || 'Untitled'}
                  </div>
                  <div className="mt-1 truncate text-[11px] text-[var(--app-sidebar-panel-muted)]">
                    {preview || 'Open saved draft'}
                  </div>
                  <div className="mt-2 text-[11px] text-[var(--app-sidebar-panel-muted)]">
                    {formatHistoryTime(String(item[dateField] || ''))}
                  </div>
                </div>
              </div>
            </button>
          );
        })}

        {count === 0 ? (
          <div className="rounded-2xl border border-dashed border-[color:var(--app-sidebar-panel-border)] px-4 py-5 text-center text-[12px] text-[var(--app-sidebar-panel-muted)]">
            {emptyLabel}
          </div>
        ) : null}
      </div>
    </div>
  );
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
  const [isLibraryMenuOpen, setIsLibraryMenuOpen] = useState(false);
  const libraryMenuRef = useRef<HTMLDivElement | null>(null);

  const libraryOptions: NavItem[] = [
    { id: 'chat', label: 'AI legal chat', icon: MessageSquare },
    { id: 'generator', label: 'Legal notice generator', icon: FileText },
    { id: 'analyzer', label: 'Document analyzer', icon: BarChart3 },
    { id: 'predictor', label: 'Win predictor', icon: TrendingUp },
  ];

  const moduleItems: NavItem[] = useMemo(() => {
    const items: NavItem[] = [{ id: 'library', label: 'Library', icon: LibraryIcon }];
    if (isAdmin) {
      items.push({ id: 'admin', label: 'Admin access', icon: ShieldCheck });
    }
    return items;
  }, [isAdmin]);

  const mobileItems: NavItem[] = isAdmin
    ? [
        { id: 'chat', label: 'Chat', icon: MessageSquare },
        { id: 'generator', label: 'Notices', icon: FileText },
        { id: 'library', label: 'Library', icon: LibraryIcon },
        { id: 'admin', label: 'Admin', icon: ShieldCheck },
        { id: 'settings', label: 'Settings', icon: Settings },
      ]
    : [
        { id: 'chat', label: 'Chat', icon: MessageSquare },
        { id: 'generator', label: 'Notices', icon: FileText },
        { id: 'library', label: 'Library', icon: LibraryIcon },
        { id: 'settings', label: 'Settings', icon: Settings },
      ];

  const activeLibrary = activeTab === 'library' || libraryOptions.some((option) => option.id === activeTab);

  useEffect(() => {
    if (!isLibraryMenuOpen) return;
    const handleClickOutside = (event: MouseEvent) => {
      const target = event.target as Node;
      if (libraryMenuRef.current && !libraryMenuRef.current.contains(target)) {
        setIsLibraryMenuOpen(false);
      }
    };
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, [isLibraryMenuOpen]);

  return (
    <>
      <aside className="fixed left-0 top-0 z-40 hidden h-screen w-72 shrink-0 border-r border-[color:var(--app-sidebar-border)] bg-[var(--app-sidebar-bg)] backdrop-blur-xl md:flex md:flex-col">
        <div className="border-b border-[color:var(--app-sidebar-border)] px-5 py-4">
          <h1 className="text-[34px] leading-none font-medium tracking-tight text-[var(--app-sidebar-brand)]">Claude</h1>
          <button type="button" className="mt-5 flex w-full items-center gap-2 rounded-lg px-2 py-2 text-left text-[23px] text-[var(--app-sidebar-fg)] hover:bg-[var(--app-sidebar-hover-bg)]" onClick={onStartNewSession}>
            <Plus size={16} />
            <span className="text-[29px]">New chat</span>
          </button>
        </div>

        <div className="flex min-h-0 flex-1 flex-col gap-5 px-4 py-5">
          <div className="space-y-1">
            <p className="px-4 text-[11px] font-medium text-[var(--app-sidebar-muted)]">Workspace</p>
            <div ref={libraryMenuRef} className="relative">
              <DesktopNavButton
                icon={LibraryIcon}
                label="Library"
                active={activeLibrary}
                onClick={() => setIsLibraryMenuOpen((prev) => !prev)}
                trailing={
                  <ChevronDown className={`h-4 w-4 transition-transform ${isLibraryMenuOpen ? 'rotate-180' : ''}`} />
                }
              />

              {isLibraryMenuOpen ? (
                <div className="app-shell-panel absolute left-full top-0 z-50 ml-3 w-72 p-2">
                  {libraryOptions.map((option) => (
                    <button
                      key={option.id}
                      type="button"
                      onClick={() => {
                        setActiveTab(option.id);
                        setIsLibraryMenuOpen(false);
                      }}
                      className={`flex w-full items-center gap-3 rounded-2xl px-3 py-3 text-left text-sm transition ${
                        activeTab === option.id
                          ? 'bg-primary/10 text-primary'
                          : 'text-on-surface-variant hover:bg-surface-container-low hover:text-on-surface'
                      }`}
                    >
                      <option.icon className="h-4 w-4" />
                      <span>{option.label}</span>
                    </button>
                  ))}
                </div>
              ) : null}
            </div>

            {moduleItems
              .filter((item) => item.id !== 'library')
              .map((item) => (
                <DesktopNavButton
                  key={item.id}
                  icon={item.icon}
                  label={item.label}
                  active={activeTab === item.id}
                  onClick={() => setActiveTab(item.id)}
                />
              ))}
          </div>

          <div className="min-h-0 flex flex-1 flex-col overflow-hidden">
            {activeTab === 'chat' ? (
              <HistoryPanel
                heading="Chat history"
                count={chatHistory.length}
                items={chatHistory as Array<Record<string, string | number | undefined>>}
                activeId={activeChatSessionId}
                emptyLabel="Your conversations will appear here once you start asking questions."
                onSelect={onSelectChatHistory}
                dateField="last_message_at"
              />
            ) : activeTab === 'generator' ? (
              <HistoryPanel
                heading="Document history"
                count={generatorHistory.length}
                items={generatorHistory as Array<Record<string, string | number | undefined>>}
                activeId={activeGeneratorHistoryId}
                emptyLabel="Generated notices and drafts will appear here."
                onSelect={onSelectGeneratorHistory}
                dateField="created_at"
              />
            ) : (
              <div className="app-shell-panel flex h-full items-center justify-center px-6 text-center text-[12px] text-[var(--app-sidebar-panel-muted)]">
                Pick a workspace from the library to begin a new legal task.
              </div>
            )}
          </div>

          <div className="shrink-0 border-t border-[color:var(--app-sidebar-border)] pt-4">
            <p className="px-4 text-[11px] font-medium text-[var(--app-sidebar-muted)]">Utilities</p>
            <div className="mt-1 space-y-1">
              <DesktopNavButton
                icon={Settings}
                label="Settings"
                active={activeTab === 'settings' && activeSettingsSection === 'details'}
                onClick={() => onSelectSettingsSection('details')}
                compact
              />
              <DesktopNavButton
                icon={KeyRound}
                label="Reset password"
                active={activeTab === 'settings' && activeSettingsSection === 'password'}
                onClick={() => onSelectSettingsSection('password')}
                compact
              />
            </div>
          </div>
        </div>
      </aside>

      <div className="fixed inset-x-0 bottom-0 z-50 border-t border-outline-variant/70 bg-surface-variant px-3 py-2 backdrop-blur-xl md:hidden">
        <div className={`grid gap-2 ${mobileItems.length === 5 ? 'grid-cols-5' : 'grid-cols-4'}`}>
          {mobileItems.map((item) => {
            const isActive =
              item.id === 'settings'
                ? activeTab === 'settings'
                : item.id === 'library'
                  ? activeLibrary
                  : activeTab === item.id;

            const handleClick = () => {
              if (item.id === 'settings') {
                onSelectSettingsSection('details');
                return;
              }
              setActiveTab(item.id);
            };

            return (
              <button
                key={item.id}
                type="button"
                onClick={handleClick}
                className={`flex flex-col items-center justify-center gap-1 rounded-2xl px-2 py-2 text-[11px] transition ${
                  isActive
                    ? 'bg-primary/10 text-primary'
                    : 'text-on-surface-variant hover:bg-surface-container-low hover:text-on-surface'
                }`}
              >
                <item.icon className="h-4 w-4" />
                <span>{item.label}</span>
              </button>
            );
          })}
        </div>
      </div>
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
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, [isProfileMenuOpen]);

  return (
    <header className="sticky top-0 z-30 flex items-center justify-end border-b border-white/10 bg-[#20201f] px-4 py-3 sm:px-6 lg:px-8">
      <div className="flex min-w-0 items-center gap-3">
        <ThemeToggle themeMode={themeMode} onToggleTheme={onToggleTheme} compact />
        <div className="relative" ref={profileMenuRef}>
          <button
            type="button"
            aria-label="Open profile menu"
            onClick={() => setIsProfileMenuOpen((prev) => !prev)}
            className="flex max-w-[min(15rem,calc(100vw-7rem))] items-center gap-3 rounded-full border border-white/10 bg-black/20 px-2 py-2 text-zinc-100 transition hover:border-white/15 hover:bg-black/30 sm:max-w-[16rem]"
          >
            <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full bg-white/10 text-xs font-semibold text-zinc-100">
              {getInitials(currentUserName)}
            </div>
            <div className="hidden min-w-0 flex-1 text-left md:block">
              <span className="block truncate text-sm font-medium text-zinc-100">{currentUserName}</span>
            </div>
            <ChevronDown size={14} className={`shrink-0 transition-transform ${isProfileMenuOpen ? 'rotate-180' : ''}`} />
          </button>

          {isProfileMenuOpen ? (
            <div className="app-shell-panel absolute right-0 top-[calc(100%+0.6rem)] z-50 w-60 overflow-hidden">
              <div className="border-b border-outline-variant/70 px-4 py-3">
                <div className="text-[11px] text-on-surface-variant">Signed in as</div>
                <div className="mt-1 text-sm font-medium text-on-surface">{currentUserName}</div>
              </div>
              <button
                type="button"
                onClick={() => {
                  setIsProfileMenuOpen(false);
                  onOpenProfile();
                }}
                className="flex w-full items-center gap-3 px-4 py-3 text-sm text-on-surface-variant transition hover:bg-surface-container-low hover:text-primary"
              >
                <Settings size={16} />
                Profile details
              </button>
              <button
                type="button"
                onClick={() => {
                  setIsProfileMenuOpen(false);
                  onLogout();
                }}
                className="flex w-full items-center gap-3 px-4 py-3 text-sm text-on-surface-variant transition hover:bg-surface-container-low hover:text-primary"
              >
                <LogOut size={16} />
                Logout
              </button>
            </div>
          ) : null}
        </div>
      </div>
    </header>
  );
};
