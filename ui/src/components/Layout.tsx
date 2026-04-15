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
}

interface HeaderProps {
  currentUserName: string;
  onLogout: () => void;
}

export const Sidebar = ({
  activeTab,
  setActiveTab,
  isAdmin,
  onStartNewSession,
  chatHistory,
  generatorHistory,
  activeChatSessionId,
  activeGeneratorHistoryId,
  onSelectChatHistory,
  onSelectGeneratorHistory,
}: SidebarProps) => {
  const [isLibraryOpen, setIsLibraryOpen] = useState(false);

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
      <aside className="fixed left-0 top-0 h-full w-64 bg-slate-100 dark:bg-slate-900 flex flex-col p-4 z-50">
      <div className="mb-6 px-2 py-4">
        <h1 className="text-xl font-headline font-bold text-primary">The Digital Atelier</h1>
        <p className="text-[10px] uppercase tracking-[0.2em] text-slate-500 font-label font-bold">Legal AI Systems</p>
      </div>

      <div className="flex-1 min-h-0 flex flex-col">
        <div className="rounded-xl border border-slate-200/70 dark:border-slate-700/60 bg-white/70 dark:bg-slate-800/60 p-4 space-y-2">
          <p className="text-[10px] uppercase tracking-[0.18em] text-slate-500 dark:text-slate-400 font-bold">
            Active Workspace
          </p>
          <div className="flex items-center gap-3 text-slate-800 dark:text-slate-100">
            {activeModule ? <activeModule.icon size={18} /> : <Library size={18} />}
            <span className="text-sm font-semibold">
              {activeModule?.label ?? 'Select from Library'}
            </span>
          </div>
          <button
            onClick={() => setIsLibraryOpen(true)}
            className="w-full mt-2 rounded-lg border border-primary/25 bg-primary/5 text-primary px-3 py-2 text-xs font-semibold hover:bg-primary/10 transition-colors"
          >
            Open Library
          </button>
        </div>

        {(showChatHistory || showGeneratorHistory) && (
          <div className="mt-4 min-h-0 rounded-xl border border-slate-200/60 dark:border-slate-700/60 bg-white/60 dark:bg-slate-800/50 p-3 flex-1 overflow-hidden">
            <div className="flex items-center justify-between mb-2">
              <p className="text-[10px] uppercase tracking-[0.14em] font-bold text-slate-500 dark:text-slate-400">
                {showChatHistory ? 'Chat History' : 'Generator History'}
              </p>
              <span className="text-[10px] text-slate-400">
                {showChatHistory ? chatHistory.length : generatorHistory.length}
              </span>
            </div>

            <div className="space-y-1 overflow-y-auto max-h-[32vh] pr-1">
              {showChatHistory &&
                chatHistory.map((item) => (
                  <button
                    key={item.session_id}
                    onClick={() => onSelectChatHistory(item.session_id)}
                    className={`w-full text-left px-2.5 py-2 rounded-lg border transition-colors ${
                      activeChatSessionId === item.session_id
                        ? 'border-primary/35 bg-primary/10 text-primary'
                        : 'border-transparent hover:border-slate-200 hover:bg-slate-100/70 dark:hover:bg-slate-800'
                    }`}
                  >
                    <div className="text-xs font-semibold truncate">{item.title || 'Untitled Chat'}</div>
                    <div className="text-[10px] text-slate-500 truncate mt-0.5">
                      {item.preview || `${item.message_count} messages`}
                    </div>
                    <div className="text-[9px] text-slate-400 mt-1">{formatHistoryTime(item.last_message_at)}</div>
                  </button>
                ))}

              {showGeneratorHistory &&
                generatorHistory.map((item) => (
                  <button
                    key={item.id}
                    onClick={() => onSelectGeneratorHistory(item.id)}
                    className={`w-full text-left px-2.5 py-2 rounded-lg border transition-colors ${
                      activeGeneratorHistoryId === item.id
                        ? 'border-primary/35 bg-primary/10 text-primary'
                        : 'border-transparent hover:border-slate-200 hover:bg-slate-100/70 dark:hover:bg-slate-800'
                    }`}
                  >
                    <div className="text-xs font-semibold truncate">{item.title || 'Generated Notice'}</div>
                    <div className="text-[10px] text-slate-500 truncate mt-0.5">
                      {item.preview || 'Open saved draft'}
                    </div>
                    <div className="text-[9px] text-slate-400 mt-1">{formatHistoryTime(item.created_at)}</div>
                  </button>
                ))}

              {showChatHistory && chatHistory.length === 0 && (
                <p className="text-[11px] text-slate-500 px-2 py-3">No chat sessions yet.</p>
              )}
              {showGeneratorHistory && generatorHistory.length === 0 && (
                <p className="text-[11px] text-slate-500 px-2 py-3">No generated notices yet.</p>
              )}
            </div>
          </div>
        )}
      </div>

      <div className="pt-4 border-t border-slate-200/30">
        <button
          onClick={onStartNewSession}
          className="w-full bg-slate-800 text-white rounded-xl py-3 px-4 flex items-center justify-center space-x-2 mb-3 hover:opacity-90 transition-opacity shadow-lg"
        >
          <Plus size={18} />
          <span className="text-sm font-semibold">New Session</span>
        </button>
        <button
          onClick={() => selectModule('generator')}
          className="w-full bg-primary text-white rounded-xl py-3 px-4 flex items-center justify-center space-x-2 mb-6 hover:opacity-90 transition-opacity shadow-lg shadow-primary/10"
        >
          <Plus size={18} />
          <span className="text-sm font-semibold">New Brief</span>
        </button>
        
        <div className="space-y-1">
          <button
            onClick={() => setIsLibraryOpen(true)}
            className={`w-full flex items-center space-x-3 px-4 py-3 rounded-lg transition-all ${
              isLibraryOpen
                ? 'bg-slate-200 dark:bg-slate-800 text-primary dark:text-white font-semibold'
                : 'text-slate-600 dark:text-slate-400 hover:text-primary dark:hover:text-white hover:bg-slate-200/50'
            }`}
          >
            <Library size={20} />
            <span className="text-sm">Library</span>
          </button>
          <button
            onClick={() => selectModule('settings')}
            className={`w-full flex items-center space-x-3 px-4 py-3 rounded-lg transition-all ${
              activeTab === 'settings'
                ? 'bg-slate-200 dark:bg-slate-800 text-primary dark:text-white font-semibold'
                : 'text-slate-600 dark:text-slate-400 hover:text-primary dark:hover:text-white hover:bg-slate-200/50'
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
            className="fixed inset-0 bg-slate-950/35 backdrop-blur-sm z-[60]"
          />
          <div className="fixed left-[17.5rem] top-1/2 -translate-y-1/2 w-[22rem] max-h-[70vh] overflow-y-auto rounded-2xl border border-slate-200/70 dark:border-slate-700/70 bg-white dark:bg-slate-900 shadow-2xl z-[70] p-4">
            <div className="flex items-center justify-between mb-4">
              <div>
                <h3 className="text-base font-bold text-primary">Library</h3>
                <p className="text-xs text-slate-500 dark:text-slate-400">Choose a workspace module</p>
              </div>
              <button
                onClick={() => setIsLibraryOpen(false)}
                className="p-2 rounded-lg text-slate-500 hover:text-primary hover:bg-slate-100 dark:hover:bg-slate-800 transition-colors"
              >
                <X size={16} />
              </button>
            </div>

            <div className="space-y-2">
              {moduleItems.map((item) => (
                <button
                  key={item.id}
                  onClick={() => selectModule(item.id)}
                  className={`w-full flex items-center space-x-3 px-4 py-3 rounded-lg transition-all ${
                    activeTab === item.id
                      ? 'bg-slate-200 dark:bg-slate-800 text-primary dark:text-white font-semibold'
                      : 'text-slate-600 dark:text-slate-400 hover:text-primary dark:hover:text-white hover:bg-slate-100 dark:hover:bg-slate-800/70'
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
    </>
  );
};

export const Header = ({ currentUserName, onLogout }: HeaderProps) => (
  <header className="sticky top-0 w-full px-8 py-4 glass-panel z-40 flex justify-between items-center">
    <div className="flex items-center">
      <span className="text-2xl font-headline italic text-primary">Vidhi AI</span>
    </div>
    
    <div className="flex items-center space-x-8">
      <nav className="flex items-center space-x-6">
        <a href="#" className="text-sm text-on-surface-variant hover:text-primary transition-colors">Explorer</a>
        <a href="#" className="text-sm font-bold text-primary border-b-2 border-primary pb-1">Workspace</a>
      </nav>
      
      <div className="flex items-center space-x-4">
        <button className="p-2 hover:bg-surface-container rounded-full transition-colors text-on-surface-variant">
          <Bell size={20} />
        </button>
        <button
          onClick={onLogout}
          className="inline-flex items-center gap-2 rounded-lg border border-outline-variant/30 px-3 py-1.5 text-xs font-semibold text-on-surface-variant hover:text-primary hover:border-primary/30"
        >
          <LogOut size={14} />
          Logout
        </button>
        <span className="text-xs font-semibold text-on-surface-variant hidden md:block">
          {currentUserName}
        </span>
        <div className="w-8 h-8 rounded-full overflow-hidden border border-outline-variant/30">
          <img 
            src="https://picsum.photos/seed/lawyer/100/100" 
            alt="User Profile" 
            className="w-full h-full object-cover"
            referrerPolicy="no-referrer"
          />
        </div>
      </div>
    </div>
  </header>
);
