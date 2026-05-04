import React from 'react';
import { Plus, MessageSquare, Settings, LogOut, ChevronDown, BookOpen } from 'lucide-react';

interface SidebarProps {
  onNewChat: () => void;
  chatHistory: { id: string; title: string; date: string }[];
}

export const Sidebar: React.FC<SidebarProps> = ({ onNewChat, chatHistory }) => {
  return (
    <div className="w-64 md:w-72 bg-surface-container flex flex-col h-full border-r border-outline-variant/20 hidden md:flex">
      {/* Workspace Header */}
      <div className="p-4 border-b border-outline-variant/20 hover:bg-surface-container-high cursor-pointer transition-colors flex items-center justify-between">
        <div className="flex items-center gap-2">
          <div className="w-8 h-8 bg-primary text-on-primary rounded-md flex items-center justify-center font-bold">
            <BookOpen size={18} />
          </div>
          <div>
            <div className="text-sm font-semibold text-on-surface">LAW LLM Workspace</div>
            <div className="text-xs text-on-surface-variant">Personal</div>
          </div>
        </div>
        <ChevronDown size={16} className="text-on-surface-variant" />
      </div>

      <div className="p-4 flex-1 overflow-y-auto">
        <button
          onClick={onNewChat}
          className="w-full flex items-center justify-center gap-2 bg-primary hover:bg-primary/90 text-on-primary rounded-xl py-2.5 px-4 font-medium transition-colors mb-6 shadow-sm"
        >
          <Plus size={18} />
          New Chat
        </button>

        <div className="text-xs font-semibold text-on-surface-variant/70 uppercase tracking-wider mb-3 px-2">
          Recent
        </div>

        <div className="space-y-1">
          {chatHistory.map((chat) => (
            <button
              key={chat.id}
              className="w-full flex items-center gap-3 px-3 py-2.5 rounded-lg hover:bg-surface-container-high transition-colors text-left group"
            >
              <MessageSquare size={16} className="text-on-surface-variant group-hover:text-primary transition-colors flex-shrink-0" />
              <div className="flex-1 overflow-hidden">
                <div className="text-sm text-on-surface truncate">{chat.title}</div>
              </div>
            </button>
          ))}
          {chatHistory.length === 0 && (
            <div className="text-sm text-on-surface-variant px-3 italic">
              No recent chats
            </div>
          )}
        </div>
      </div>

      {/* Utilities */}
      <div className="p-4 border-t border-outline-variant/20 space-y-1">
        <button className="w-full flex items-center gap-3 px-3 py-2 rounded-lg hover:bg-surface-container-high transition-colors text-sm text-on-surface-variant hover:text-on-surface">
          <Settings size={16} />
          Settings
        </button>
        <button className="w-full flex items-center gap-3 px-3 py-2 rounded-lg hover:bg-surface-container-high transition-colors text-sm text-on-surface-variant hover:text-on-surface">
          <LogOut size={16} />
          Reset Password
        </button>
      </div>
    </div>
  );
};
