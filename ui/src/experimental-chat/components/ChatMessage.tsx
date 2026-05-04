import React from 'react';
import ReactMarkdown from 'react-markdown';
import { User, Bot } from 'lucide-react';

export interface Message {
  id: string;
  role: 'user' | 'assistant';
  content: string;
}

interface ChatMessageProps {
  message: Message;
}

export const ChatMessage: React.FC<ChatMessageProps> = ({ message }) => {
  const isUser = message.role === 'user';

  return (
    <div className={`flex w-full ${isUser ? 'justify-end' : 'justify-start'} mb-6`}>
      <div className={`flex max-w-[85%] md:max-w-[75%] ${isUser ? 'flex-row-reverse' : 'flex-row'} gap-3`}>
        <div className={`flex-shrink-0 w-8 h-8 rounded-full flex items-center justify-center ${isUser ? 'bg-primary text-on-primary' : 'bg-secondary text-on-secondary'}`}>
          {isUser ? <User size={18} /> : <Bot size={18} />}
        </div>
        <div className={`flex flex-col ${isUser ? 'items-end' : 'items-start'}`}>
          <div className="text-xs text-on-surface-variant mb-1 mx-1 font-medium">
            {isUser ? 'You' : 'AI Assistant'}
          </div>
          <div 
            className={`p-4 rounded-2xl text-sm md:text-base leading-relaxed ${
              isUser 
                ? 'bg-primary text-on-primary rounded-tr-sm' 
                : 'bg-surface-container-low text-on-surface rounded-tl-sm border border-outline-variant/20 shadow-sm'
            }`}
          >
            {isUser ? (
              <div className="whitespace-pre-wrap">{message.content}</div>
            ) : (
              <div className="prose prose-sm dark:prose-invert prose-p:leading-relaxed prose-pre:bg-surface-container prose-pre:border prose-pre:border-outline-variant/30 max-w-none">
                <ReactMarkdown>{message.content}</ReactMarkdown>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
};
