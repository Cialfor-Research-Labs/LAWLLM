import React from 'react';
import { motion } from 'motion/react';

export const TypingIndicator: React.FC = () => {
  return (
    <div className="flex items-center space-x-1 p-4 bg-surface-container-low rounded-2xl rounded-tl-sm w-fit">
      <motion.div
        className="w-2 h-2 bg-on-surface-variant rounded-full"
        animate={{ y: [0, -5, 0] }}
        transition={{ duration: 0.6, repeat: Infinity, delay: 0 }}
      />
      <motion.div
        className="w-2 h-2 bg-on-surface-variant rounded-full"
        animate={{ y: [0, -5, 0] }}
        transition={{ duration: 0.6, repeat: Infinity, delay: 0.2 }}
      />
      <motion.div
        className="w-2 h-2 bg-on-surface-variant rounded-full"
        animate={{ y: [0, -5, 0] }}
        transition={{ duration: 0.6, repeat: Infinity, delay: 0.4 }}
      />
    </div>
  );
};
