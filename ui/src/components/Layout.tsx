import React from 'react';
import { 
  MessageSquare, 
  FileText, 
  BarChart3, 
  TrendingUp, 
  Plus, 
  Library, 
  Settings, 
  Bell 
} from 'lucide-react';

interface NavItem {
  id: string;
  label: string;
  icon: React.ElementType;
}

export const Sidebar = ({ activeTab, setActiveTab }: { activeTab: string, setActiveTab: (id: string) => void }) => {
  const navItems: NavItem[] = [
    { id: 'chat', label: 'AI Legal Chat', icon: MessageSquare },
    { id: 'generator', label: 'Document Generator', icon: FileText },
    { id: 'analyzer', label: 'Document Analyzer', icon: BarChart3 },
    { id: 'predictor', label: 'Win Predictor', icon: TrendingUp },
  ];

  return (
    <aside className="fixed left-0 top-0 h-full w-64 bg-slate-100 dark:bg-slate-900 flex flex-col p-4 z-50">
      <div className="mb-8 px-2 py-4">
        <h1 className="text-xl font-headline font-bold text-primary">The Digital Atelier</h1>
        <p className="text-[10px] uppercase tracking-[0.2em] text-slate-500 font-label font-bold">Legal AI Systems</p>
      </div>

      <nav className="flex-1 space-y-1">
        {navItems.map((item) => (
          <button
            key={item.id}
            onClick={() => setActiveTab(item.id)}
            className={`w-full flex items-center space-x-3 px-4 py-3 rounded-lg transition-all ${
              activeTab === item.id 
                ? 'bg-slate-200 dark:bg-slate-800 text-primary dark:text-white font-semibold' 
                : 'text-slate-600 dark:text-slate-400 hover:text-primary dark:hover:text-white hover:bg-slate-200/50'
            }`}
          >
            <item.icon size={20} />
            <span className="text-sm">{item.label}</span>
          </button>
        ))}
      </nav>

      <div className="pt-4 border-t border-slate-200/30">
        <button className="w-full bg-primary text-white rounded-xl py-3 px-4 flex items-center justify-center space-x-2 mb-6 hover:opacity-90 transition-opacity shadow-lg shadow-primary/10">
          <Plus size={18} />
          <span className="text-sm font-semibold">New Brief</span>
        </button>
        
        <div className="space-y-1">
          <button className="w-full flex items-center space-x-3 px-4 py-3 text-slate-600 dark:text-slate-400 hover:text-primary transition-all">
            <Library size={20} />
            <span className="text-sm">Library</span>
          </button>
          <button className="w-full flex items-center space-x-3 px-4 py-3 text-slate-600 dark:text-slate-400 hover:text-primary transition-all">
            <Settings size={20} />
            <span className="text-sm">Settings</span>
          </button>
        </div>
      </div>
    </aside>
  );
};

export const Header = () => (
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
