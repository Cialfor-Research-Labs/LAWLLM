import React, { useMemo, useState } from 'react';
import { motion } from 'motion/react';
import { Bot, Braces, FileText, ShieldCheck, Sparkles, TerminalSquare } from 'lucide-react';

interface LibraryLandingProps {
  onOpenChat: () => void;
  onOpenGenerator: () => void;
  onOpenAnalyzer: () => void;
  trustedCount: number;
}

const TABS = ['JSON', 'Preview', 'Logs'] as const;

export const LibraryLanding = ({ onOpenChat, onOpenGenerator, onOpenAnalyzer, trustedCount }: LibraryLandingProps) => {
  const [activeTab, setActiveTab] = useState<(typeof TABS)[number]>('JSON');
  const sampleOutput = useMemo(() => {
    if (activeTab === 'Preview') {
      return 'Matter summary ready.\n- Key issues identified\n- Next legal actions suggested';
    }
    if (activeTab === 'Logs') {
      return '[11:42:08] intake: accepted\n[11:42:09] retrieval: 6 sources\n[11:42:11] response: complete';
    }
    return '{\n  "status": "complete",\n  "confidence": 0.91,\n  "issue": "salary_recovery",\n  "next_steps": ["Send notice", "Preserve evidence"]\n}';
  }, [activeTab]);

  return (
    <div className="flex-1 overflow-y-auto px-4 pb-16 pt-6 sm:px-8">
      <section className="mx-auto w-full max-w-6xl">
        <div className="glass-panel relative overflow-hidden rounded-[28px] p-8 sm:p-10">
          <div className="pointer-events-none absolute -right-32 -top-24 h-72 w-72 rounded-full bg-gradient-to-br from-cyan-400/20 to-indigo-500/20 blur-3xl" />
          <div className="pointer-events-none absolute -left-16 bottom-0 h-52 w-52 rounded-full bg-gradient-to-br from-indigo-500/20 to-blue-400/20 blur-3xl" />
          <div className="relative z-10">
            <div className="inline-flex items-center gap-2 rounded-full border border-white/10 bg-white/5 px-3 py-1 text-xs text-on-surface-variant">
              <Sparkles size={14} className="text-cyan-300" />
              Developer-first legal workspace
            </div>
            <h1 className="mt-5 max-w-3xl text-4xl font-semibold leading-tight text-white sm:text-6xl">
              Build legal outputs with the speed of an API playground
            </h1>
            <p className="mt-4 max-w-2xl text-sm leading-7 text-on-surface-variant sm:text-base">
              Ask complex legal questions, generate notices, and iterate quickly in one focused interface.
            </p>
            <div className="mt-7 flex flex-col gap-3 sm:flex-row">
              <button type="button" className="primary-button" onClick={onOpenChat}>
                Start with Legal Chat
              </button>
              <button type="button" className="secondary-button" onClick={onOpenGenerator}>
                Open Notice Generator
              </button>
            </div>
          </div>
        </div>
      </section>

      <section id="features" className="mx-auto mt-8 grid w-full max-w-6xl gap-4 md:grid-cols-3">
        {[
          { icon: Bot, title: 'Reasoning Chat', description: 'Multi-turn legal interview with context memory.' },
          { icon: FileText, title: 'Draft Engine', description: 'Structured notice generation with confidence signals.' },
          { icon: ShieldCheck, title: 'Secure Access', description: 'Role-aware workflows with admin approval gates.' },
        ].map((item) => (
          <motion.button
            whileHover={{ y: -4 }}
            key={item.title}
            onClick={item.title === 'Draft Engine' ? onOpenGenerator : onOpenChat}
            className="glass-panel rounded-3xl p-6 text-left transition hover:border-primary/50"
          >
            <item.icon className="h-6 w-6 text-cyan-300" />
            <h3 className="mt-4 text-lg font-semibold text-white">{item.title}</h3>
            <p className="mt-2 text-sm leading-7 text-on-surface-variant">{item.description}</p>
          </motion.button>
        ))}
      </section>

      <section className="mx-auto mt-8 grid w-full max-w-6xl gap-5 lg:grid-cols-[1fr_1.1fr]">
        <div className="glass-panel rounded-3xl p-6">
          <div className="mb-3 flex items-center gap-2 text-sm text-on-surface-variant">
            <TerminalSquare size={16} />
            Input
          </div>
          <textarea
            readOnly
            value="Employee was unpaid for 3 months despite written reminders. Draft legal strategy and notice path."
            className="text-field min-h-[150px] resize-none"
          />
          <div className="mt-4 flex gap-3">
            <button type="button" className="primary-button" onClick={onOpenChat}>
              Run Analysis
            </button>
            <button type="button" className="neutral-button" onClick={onOpenAnalyzer}>
              Open Analyzer
            </button>
          </div>
        </div>

        <div className="glass-panel rounded-3xl p-6">
          <div className="mb-4 flex items-center justify-between">
            <div className="flex items-center gap-2 text-sm text-on-surface-variant">
              <Braces size={16} />
              Output
            </div>
            <div className="flex gap-2">
              {TABS.map((tab) => (
                <button
                  key={tab}
                  type="button"
                  onClick={() => setActiveTab(tab)}
                  className={`rounded-xl px-3 py-1.5 text-xs transition ${activeTab === tab ? 'bg-primary text-white' : 'bg-surface-container text-on-surface-variant'}`}
                >
                  {tab}
                </button>
              ))}
            </div>
          </div>
          <pre className="rounded-2xl border border-outline-variant/70 bg-[#0a1220] p-4 font-mono text-xs leading-6 text-cyan-200">
            {sampleOutput}
          </pre>
        </div>
      </section>

      <section id="pricing" className="mx-auto mt-8 w-full max-w-6xl">
        <div className="glass-panel rounded-3xl p-6 sm:p-7">
          <div className="grid gap-4 sm:grid-cols-3">
            <div>
              <p className="text-sm text-on-surface-variant">Trusted by</p>
              <p className="mt-1 text-3xl font-semibold text-white">{Math.max(trustedCount, 1200)}+</p>
              <p className="text-sm text-on-surface-variant">active users</p>
            </div>
            <div>
              <p className="text-sm text-on-surface-variant">Avg response</p>
              <p className="mt-1 text-3xl font-semibold text-white">2.4s</p>
            </div>
            <div>
              <p className="text-sm text-on-surface-variant">Workflows</p>
              <p className="mt-1 text-3xl font-semibold text-white">Chat, Draft, Analyze</p>
            </div>
          </div>
        </div>
      </section>

      <footer id="docs" className="mx-auto mt-8 w-full max-w-6xl pb-6">
        <div className="flex flex-col items-start justify-between gap-4 border-t border-outline-variant/70 pt-5 text-sm text-on-surface-variant sm:flex-row sm:items-center">
          <p>Legal AI Workspace</p>
          <div className="flex items-center gap-4">
            <a href="#docs" className="transition hover:text-white">Docs</a>
            <a href="#features" className="transition hover:text-white">Features</a>
            <a href="#pricing" className="transition hover:text-white">Pricing</a>
          </div>
        </div>
      </footer>
    </div>
  );
};
