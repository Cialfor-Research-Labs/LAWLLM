import React, { useState } from 'react';
import { Sidebar } from './components/Sidebar';
import { ChatContainer } from './components/ChatContainer';
import { Message } from './components/ChatMessage';
import { getMockResponse } from './mock/mockLLM';

function getTllacApiUrl(): string {
  const configured = import.meta.env.VITE_TLLAC_API_URL?.trim();
  if (configured) {
    return configured.replace(/\/$/, '');
  }
  return '/tllac-api/chat';
}

interface ChatPageProps {
  embedded?: boolean;
  onHistoryChange?: (history: any[]) => void;
}

export const ChatPage: React.FC<ChatPageProps> = ({ embedded = false, onHistoryChange }) => {
  const tllacApiUrl = getTllacApiUrl();
  const [messages, setMessages] = useState<Message[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [chatHistory, setChatHistory] = useState<{ id: string; title: string; date: string; last_message_at: string }[]>([]);

  const handleSendMessage = async (content: string) => {
    // Add user message
    const userMessage: Message = {
      id: Date.now().toString(),
      role: 'user',
      content
    };
    
    setMessages(prev => [...prev, userMessage]);
    setIsLoading(true);

    // Update history if first message
    if (messages.length === 0) {
      const newHistoryItem = { 
        id: Date.now().toString(), 
        session_id: Date.now().toString(),
        title: content.slice(0, 30) + (content.length > 30 ? '...' : ''), 
        date: new Date().toISOString(),
        last_message_at: new Date().toISOString()
      };
      const newHistory = [newHistoryItem, ...chatHistory];
      setChatHistory(newHistory);
      onHistoryChange?.(newHistory);
    }

    let responseText: string;

    try {
      // Route through a configurable same-origin endpoint by default so
      // the trained chat works on localhost and LAN-hosted dev sessions.
      const res = await fetch(tllacApiUrl, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ query: content }),
      });

      if (!res.ok) {
        throw new Error(`Backend error: ${res.status}`);
      }

      const data = await res.json();
      responseText = data.response;
    } catch {
      // Fallback to mock if backend is unreachable
      responseText = getMockResponse(content);
    }

    const botMessage: Message = {
      id: (Date.now() + 1).toString(),
      role: 'assistant',
      content: responseText,
    };
    setMessages(prev => [...prev, botMessage]);
    setIsLoading(false);
  };

  const handleNewChat = () => {
    setMessages([]);
    setIsLoading(false);
  };

  const content = (
    <>
      {/* Mobile Header - only show if not embedded or on mobile */}
      <div className={`${embedded ? 'hidden' : 'md:hidden'} flex items-center p-4 border-b border-outline-variant/20 bg-surface-container`}>
        <div className="font-semibold">LAW LLM Assistant</div>
      </div>
      <ChatContainer 
        messages={messages} 
        isLoading={isLoading} 
        onSendMessage={handleSendMessage} 
      />
    </>
  );

  if (embedded) {
    return <div className="flex-1 flex flex-col relative z-10 w-full h-full">{content}</div>;
  }

  return (
    <div className="flex h-screen overflow-hidden bg-surface font-body text-on-surface" data-theme="dark">
      <Sidebar onNewChat={handleNewChat} chatHistory={chatHistory} />
      <div className="flex-1 flex flex-col relative z-10 w-full md:w-auto">
        {content}
      </div>
    </div>
  );
};

export default ChatPage;
