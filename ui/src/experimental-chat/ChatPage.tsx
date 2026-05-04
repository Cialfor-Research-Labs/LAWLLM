import React, { useState } from 'react';
import { Sidebar } from './components/Sidebar';
import { ChatContainer } from './components/ChatContainer';
import { Message } from './components/ChatMessage';

const DEFAULT_TLLAC_API_URL = '/tllac-api/chat';
const LOCAL_TLLAC_API_URL = 'http://127.0.0.1:9001/chat';

function normalizeTllacApiUrl(url: string): string {
  const trimmed = url.trim().replace(/\/$/, '');
  return trimmed.endsWith('/chat') ? trimmed : `${trimmed}/chat`;
}

function isLocalhostUrl(url: string): boolean {
  return /^https?:\/\/(localhost|127\.0\.0\.1)(:\d+)?(\/|$)/i.test(url);
}

function shouldPreferProxy(configuredUrl: string): boolean {
  const hostname = window.location.hostname;
  const isLocalBrowser =
    hostname === 'localhost' ||
    hostname === '127.0.0.1' ||
    hostname === '';

  return isLocalhostUrl(configuredUrl) && !isLocalBrowser;
}

function getConfiguredTllacApiUrl(): string | null {
  const configured = import.meta.env.VITE_TLLAC_API_URL?.trim();
  if (configured) {
    return normalizeTllacApiUrl(configured);
  }
  return null;
}

function getHostBasedTllacApiUrl(): string {
  const { protocol, hostname } = window.location;
  const resolvedProtocol = protocol === 'https:' ? 'https:' : 'http:';
  const resolvedHostname = hostname || '127.0.0.1';
  return `${resolvedProtocol}//${resolvedHostname}:9001/chat`;
}

async function requestChatResponse(url: string, query: string): Promise<string> {
  const res = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ query }),
  });

  if (!res.ok) {
    throw new Error(`Backend error: ${res.status}`);
  }

  const data = await res.json();
  const responseText = typeof data?.response === 'string' ? data.response.trim() : '';
  if (!responseText) {
    throw new Error('Backend returned an empty response.');
  }
  return responseText;
}

interface ChatPageProps {
  embedded?: boolean;
  onHistoryChange?: (history: any[]) => void;
}

export const ChatPage: React.FC<ChatPageProps> = ({ embedded = false, onHistoryChange }) => {
  const configuredTllacApiUrl = getConfiguredTllacApiUrl();
  const hostBasedTllacApiUrl = getHostBasedTllacApiUrl();
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
      const candidateUrls: string[] = [];

      if (configuredTllacApiUrl && !shouldPreferProxy(configuredTllacApiUrl)) {
        candidateUrls.push(configuredTllacApiUrl);
      }
      if (!candidateUrls.includes(DEFAULT_TLLAC_API_URL)) {
        candidateUrls.push(DEFAULT_TLLAC_API_URL);
      }
      if (!candidateUrls.includes(hostBasedTllacApiUrl)) {
        candidateUrls.push(hostBasedTllacApiUrl);
      }
      if (!candidateUrls.includes(LOCAL_TLLAC_API_URL)) {
        candidateUrls.push(LOCAL_TLLAC_API_URL);
      }
      if (configuredTllacApiUrl && !candidateUrls.includes(configuredTllacApiUrl)) {
        candidateUrls.push(configuredTllacApiUrl);
      }

      let lastError: unknown = null;
      responseText = '';

      for (const candidateUrl of candidateUrls) {
        try {
          responseText = await requestChatResponse(candidateUrl, content);
          break;
        } catch (error) {
          lastError = error;
        }
      }

      if (!responseText) {
        throw lastError ?? new Error('Unable to reach the trained chat backend.');
      }
    } catch (error) {
      const reason = error instanceof Error ? error.message : 'Unknown backend error';
      responseText = `The trained legal chat backend is unavailable right now.\n\nDetails: ${reason}`;
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
