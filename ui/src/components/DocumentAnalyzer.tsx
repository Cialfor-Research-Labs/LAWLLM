import React from 'react';
import { Search } from 'lucide-react';
import { motion } from 'motion/react';

export const DocumentAnalyzer = () => {
  return (
    <div className="flex-1 flex flex-col h-full bg-surface items-center justify-center">
      <motion.div 
        initial={{ opacity: 0, scale: 0.9 }}
        animate={{ opacity: 1, scale: 1 }}
        className="text-center space-y-6 p-12"
      >
        <div className="w-24 h-24 bg-primary/10 rounded-full flex items-center justify-center text-primary mx-auto mb-8">
          <Search size={48} />
        </div>
        <h1 className="text-6xl font-headline italic text-primary">Coming Soon</h1>
        <p className="text-xl text-on-surface-variant font-body max-w-md mx-auto">
          Our intelligent legal document analysis and compliance checker is currently under development.
        </p>
        <div className="pt-8">
          <div className="inline-block px-6 py-2 rounded-full bg-surface-container border border-outline-variant text-sm font-label tracking-widest uppercase text-on-surface-variant">
            Stay Tuned
          </div>
        </div>
      </motion.div>
    </div>
  );
};
