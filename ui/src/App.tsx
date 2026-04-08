/**
 * @license
 * SPDX-License-Identifier: Apache-2.0
 */

import React, { useState } from 'react';
import { Search } from 'lucide-react';
import { motion, AnimatePresence } from 'motion/react';
import { Sidebar, Header } from './components/Layout';
import { DocumentAnalyzer } from './components/DocumentAnalyzer';
import { LegalChat } from './components/LegalChat';
import { DocumentGenerator } from './components/DocumentGenerator';
import { WinPredictor } from './components/WinPredictor';

export default function App() {
  const [activeTab, setActiveTab] = useState('chat');

  return (
    <div className="flex min-h-screen bg-surface font-body overflow-hidden">
      <Sidebar activeTab={activeTab} setActiveTab={setActiveTab} />
      
      <main className="flex-1 ml-64 flex flex-col h-screen relative">
        <Header />
        
        <AnimatePresence mode="wait">
          {activeTab === 'analyzer' ? (
            <motion.div 
              key="analyzer"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              className="flex-1 flex flex-col overflow-hidden"
            >
              <DocumentAnalyzer />
            </motion.div>
          ) : activeTab === 'chat' ? (
            <motion.div 
              key="chat"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              className="flex-1 flex flex-col overflow-hidden"
            >
              <LegalChat />
            </motion.div>
          ) : activeTab === 'generator' ? (
            <motion.div 
              key="generator"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              className="flex-1 flex flex-col overflow-hidden"
            >
              <DocumentGenerator />
            </motion.div>
          ) : activeTab === 'predictor' ? (
            <motion.div 
              key="predictor"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              className="flex-1 flex flex-col overflow-hidden"
            >
              <WinPredictor />
            </motion.div>
          ) : (
            <motion.div 
              key="placeholder"
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -20 }}
              className="flex-1 flex items-center justify-center p-8"
            >
              <div className="text-center space-y-4 max-w-md">
                <div className="w-16 h-16 bg-surface-container rounded-full flex items-center justify-center mx-auto text-on-surface-variant">
                  <Search size={32} />
                </div>
                <h2 className="text-2xl font-headline font-bold text-primary">
                  {activeTab.charAt(0).toUpperCase() + activeTab.slice(1).replace(/([A-Z])/g, ' $1')} Module
                </h2>
                <p className="text-on-surface-variant">
                  This module is currently in development. Please use the Document Analyzer to review legal agreements.
                </p>
              </div>
            </motion.div>
          )}
        </AnimatePresence>
      </main>
    </div>
  );
}
