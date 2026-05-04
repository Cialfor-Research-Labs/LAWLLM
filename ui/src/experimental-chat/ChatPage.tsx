import React, { useState } from 'react';
import { Sidebar } from './components/Sidebar';
import { ChatContainer } from './components/ChatContainer';
import { Message } from './components/ChatMessage';
import { getMockResponse } from './mock/mockLLM';

export const ChatPage: React.FC = () => {
  const [messages, setMessages] = useState<Message[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [chatHistory, setChatHistory] = useState<{ id: string; title: string; date: string }[]>([]);

  const handleSendMessage = (content: string) => {
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
      setChatHistory(prev => [
        { id: Date.now().toString(), title: content.slice(0, 30) + (content.length > 30 ? '...' : ''), date: new Date().toISOString() },
        ...prev
      ]);
    }

    // Simulate typing and network delay
    setTimeout(() => {
      const botMessage: Message = {
        id: (Date.now() + 1).toString(),
        role: 'assistant',
        content: getMockResponse(content)
      };
      setMessages(prev => [...prev, botMessage]);
      setIsLoading(false);
    }, 1200);
  };

  const handleNewChat = () => {
    setMessages([]);
    setIsLoading(false);
  };

  return (
    <div className="flex h-screen overflow-hidden bg-surface font-body text-on-surface" data-theme="dark">
      <Sidebar onNewChat={handleNewChat} chatHistory={chatHistory} />
      <div className="flex-1 flex flex-col relative z-10 w-full md:w-auto">
        {/* Mobile Header */}
        <div className="md:hidden flex items-center p-4 border-b border-outline-variant/20 bg-surface-container">
          <div className="font-semibold">LAW LLM Assistant</div>
        </div>
        <ChatContainer 
          messages={messages} 
          isLoading={isLoading} 
          onSendMessage={handleSendMessage} 
        />
      </div>
    </div>
  );
};

export default ChatPage;
