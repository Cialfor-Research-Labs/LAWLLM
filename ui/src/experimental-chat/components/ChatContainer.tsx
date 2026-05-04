import React, { useRef, useEffect } from 'react';
import { ChatMessage, Message } from './ChatMessage';
import { ChatInput } from './ChatInput';
import { TypingIndicator } from './TypingIndicator';

interface ChatContainerProps {
  messages: Message[];
  isLoading: boolean;
  onSendMessage: (content: string) => void;
}

export const ChatContainer: React.FC<ChatContainerProps> = ({ messages, isLoading, onSendMessage }) => {
  const messagesEndRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, isLoading]);

  const suggestedPrompts = [
    "Explain contract law in simple terms",
    "What is adverse possession?",
    "Latest AI regulations",
    "How property disputes work in India"
  ];

  return (
    <div className="flex-1 flex flex-col h-full bg-surface">
      <div className="flex-1 overflow-y-auto px-4 py-6 md:px-8">
        <div className="max-w-4xl mx-auto flex flex-col min-h-full justify-between">
          <div>
            {messages.length === 0 ? (
              <div className="flex flex-col items-center justify-center pt-20 pb-10 text-center">
                <div className="w-16 h-16 bg-primary/10 text-primary rounded-2xl flex items-center justify-center mb-6">
                  <span className="text-3xl">✨</span>
                </div>
                <h1 className="text-2xl font-semibold text-on-surface mb-2">
                  Hello, I’m your AI Research Assistant.
                </h1>
                <p className="text-on-surface-variant max-w-md mx-auto mb-12">
                  Ask anything — I’ll provide structured answers based on internal knowledge.
                </p>
                
                <div className="w-full max-w-2xl mx-auto grid grid-cols-1 md:grid-cols-2 gap-3">
                  {suggestedPrompts.map((prompt, index) => (
                    <button
                      key={index}
                      onClick={() => onSendMessage(prompt)}
                      className="p-4 text-left rounded-xl border border-outline-variant/30 bg-surface-container-low hover:bg-surface-container hover:border-primary/50 transition-all text-sm text-on-surface-variant hover:text-on-surface shadow-sm"
                    >
                      {prompt}
                    </button>
                  ))}
                </div>
              </div>
            ) : (
              <div className="pb-4">
                {messages.map((message) => (
                  <ChatMessage key={message.id} message={message} />
                ))}
                {isLoading && (
                  <div className="flex w-full justify-start mb-6">
                    <div className="flex max-w-[85%] md:max-w-[75%] flex-row gap-3">
                      <div className="flex-shrink-0 w-8 h-8 rounded-full flex items-center justify-center bg-secondary text-on-secondary">
                        <span className="text-sm font-bold">AI</span>
                      </div>
                      <div className="flex flex-col items-start">
                        <div className="text-xs text-on-surface-variant mb-1 mx-1 font-medium">
                          AI Assistant
                        </div>
                        <TypingIndicator />
                      </div>
                    </div>
                  </div>
                )}
              </div>
            )}
            <div ref={messagesEndRef} />
          </div>
        </div>
      </div>
      <ChatInput onSend={onSendMessage} disabled={isLoading} />
    </div>
  );
};
