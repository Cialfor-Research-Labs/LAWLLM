import React, { useState, KeyboardEvent } from 'react';
import { Send } from 'lucide-react';

interface ChatInputProps {
  onSend: (message: string) => void;
  disabled: boolean;
}

export const ChatInput: React.FC<ChatInputProps> = ({ onSend, disabled }) => {
  const [input, setInput] = useState('');

  const handleSend = () => {
    if (input.trim() && !disabled) {
      onSend(input.trim());
      setInput('');
    }
  };

  const handleKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  return (
    <div className="p-4 bg-surface/80 backdrop-blur-sm border-t border-outline-variant/30">
      <div className="max-w-4xl mx-auto relative flex items-center">
        <textarea
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="Ask anything..."
          disabled={disabled}
          className="w-full resize-none rounded-2xl bg-surface-container-low px-4 py-3 pr-12 text-on-surface placeholder:text-on-surface-variant/50 focus:outline-none focus:ring-1 focus:ring-primary/50 disabled:opacity-50"
          rows={1}
          style={{ minHeight: '52px', maxHeight: '200px' }}
        />
        <button
          onClick={handleSend}
          disabled={disabled || !input.trim()}
          className="absolute right-2 p-2 rounded-full text-primary hover:bg-primary/10 disabled:opacity-50 disabled:hover:bg-transparent transition-colors"
        >
          <Send size={20} />
        </button>
      </div>
    </div>
  );
};
