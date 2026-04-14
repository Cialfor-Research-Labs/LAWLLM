import React, { useEffect, useMemo, useState } from 'react';
import { motion, AnimatePresence } from 'motion/react';
import Markdown from 'react-markdown';
import type { Components } from 'react-markdown';
import {
  FileText,
  Plus,
  Trash2,
  Loader2,
  Download,
  Copy,
  CheckCircle2,
  AlertCircle,
  ChevronDown,
  Sparkles,
  Scale,
  Shield,
  Zap,
} from 'lucide-react';

// ---- Types ----

interface NoticeType {
  id: string;
  label: string;
}

interface NoticeResponse {
  ok: boolean;
  notice: string;
  laws_used: string[];
  notice_type: string;
  notice_type_label: string;
  confidence: number;
  confidence_label: string;
  meta?: Record<string, unknown>;
}

type Tone = 'firm' | 'aggressive' | 'polite';

interface GeneratorFormSnapshot {
  senderName: string;
  receiverName: string;
  relationship: string;
  facts: string[];
  claim: string;
  noticeType: string;
  tone: Tone;
  deadline: number | '';
  customRelief: string;
}

interface GeneratorHistoryItem {
  id: string;
  title: string;
  created_at: string;
  preview: string;
  form: GeneratorFormSnapshot;
  result: NoticeResponse;
}

interface DocumentGeneratorProps {
  authToken: string;
  openHistoryRequest?: { id: string; nonce: number } | null;
  onHistoryChange?: (items: Array<{ id: string; title: string; created_at: string; preview?: string }>) => void;
  onActiveHistoryChange?: (id: string | null) => void;
}

// ---- API ----

function getApiBase(): string {
  const configured = import.meta.env.VITE_API_BASE_URL?.trim();
  if (configured) {
    return configured.replace(/\/$/, '');
  }
  return '/api';
}

const markdownComponents: Components = {
  strong: ({ children }) => <strong className="font-extrabold text-primary">{children}</strong>,
  p: ({ children }) => <p className="mb-3 last:mb-0 leading-7">{children}</p>,
  ol: ({ children }) => <ol className="mb-3 ml-5 list-decimal space-y-1">{children}</ol>,
  ul: ({ children }) => <ul className="mb-3 ml-5 list-disc space-y-1">{children}</ul>,
  li: ({ children }) => <li className="pl-1 leading-7">{children}</li>,
  h1: ({ children }) => <h1 className="text-xl font-bold text-primary mt-4 mb-2">{children}</h1>,
  h2: ({ children }) => <h2 className="text-lg font-bold text-primary mt-3 mb-2">{children}</h2>,
  h3: ({ children }) => <h3 className="text-base font-bold mt-2 mb-1">{children}</h3>,
  hr: () => <hr className="my-4 border-outline-variant/20" />,
};

const TONE_OPTIONS: { id: Tone; label: string; description: string; icon: React.ElementType }[] = [
  { id: 'polite', label: 'Polite', description: 'Professional and measured', icon: Shield },
  { id: 'firm', label: 'Firm', description: 'Direct and assertive', icon: Scale },
  { id: 'aggressive', label: 'Aggressive', description: 'Strong and urgent', icon: Zap },
];

const CONFIDENCE_COLORS: Record<string, string> = {
  high: 'text-emerald-700 bg-emerald-50 border-emerald-200',
  medium: 'text-amber-700 bg-amber-50 border-amber-200',
  low: 'text-orange-700 bg-orange-50 border-orange-200',
  very_low: 'text-rose-700 bg-rose-50 border-rose-200',
};

const GENERATOR_HISTORY_KEY = 'vidhi_generator_history_v1';
const GENERATOR_HISTORY_LIMIT = 40;

// ---- Component ----

export const DocumentGenerator = ({
  authToken,
  openHistoryRequest,
  onHistoryChange,
  onActiveHistoryChange,
}: DocumentGeneratorProps) => {
  const apiBase = useMemo(() => getApiBase(), []);
  const authHeaders = useMemo(
    () => ({
      'Content-Type': 'application/json',
      Authorization: `Bearer ${authToken}`,
    }),
    [authToken],
  );

  // Form state
  const [senderName, setSenderName] = useState('');
  const [receiverName, setReceiverName] = useState('');
  const [relationship, setRelationship] = useState('');
  const [facts, setFacts] = useState<string[]>(['']);
  const [claim, setClaim] = useState('');
  const [noticeType, setNoticeType] = useState('auto');
  const [tone, setTone] = useState<Tone>('firm');
  const [deadline, setDeadline] = useState<number | ''>('');
  const [customRelief, setCustomRelief] = useState('');

  // Data
  const [noticeTypes, setNoticeTypes] = useState<NoticeType[]>([]);
  const [result, setResult] = useState<NoticeResponse | null>(null);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState('');
  const [copied, setCopied] = useState(false);
  const [showTypeDropdown, setShowTypeDropdown] = useState(false);
  const [historyItems, setHistoryItems] = useState<GeneratorHistoryItem[]>([]);
  const [activeHistoryId, setActiveHistoryId] = useState<string | null>(null);

  // Fetch notice types on mount
  useEffect(() => {
    fetch(`${apiBase}/generate/notice-types`, {
      headers: { Authorization: `Bearer ${authToken}` },
    })
      .then((res) => {
        if (!res.ok) throw new Error(`Unable to load notice types (${res.status})`);
        return res.json();
      })
      .then((data) => {
        if (data.ok) setNoticeTypes(data.types || []);
      })
      .catch((err) => {
        setError(err instanceof Error ? err.message : 'Failed to load notice types');
      });
  }, [apiBase, authToken]);

  // Sync with AI Legal Chat
  useEffect(() => {
    const handleSync = () => {
      const pendingDraft = localStorage.getItem('pending_legal_notice');
      if (pendingDraft) {
        // Construct a mock successful response from the synced data
        const syncedResult: NoticeResponse = {
            ok: true,
            notice: pendingDraft,
            laws_used: [], // Optional: could parse from draft if needed
            notice_type: 'synced',
            notice_type_label: 'Imported from Chat',
            confidence: 1.0,
            confidence_label: 'high',
            meta: { synced: true }
        };
        setResult(syncedResult);
        localStorage.removeItem('pending_legal_notice'); // Consume the draft
      }
    };

    // Check on mount and periodically or via event (custom event)
    handleSync();
    const interval = setInterval(handleSync, 2000); 
    return () => clearInterval(interval);
  }, []);

  const toHistorySummary = (items: GeneratorHistoryItem[]) =>
    items.map((item) => ({
      id: item.id,
      title: item.title,
      created_at: item.created_at,
      preview: item.preview,
    }));

  const applyHistoryItem = (item: GeneratorHistoryItem) => {
    setSenderName(item.form.senderName);
    setReceiverName(item.form.receiverName);
    setRelationship(item.form.relationship);
    setFacts(item.form.facts?.length ? item.form.facts : ['']);
    setClaim(item.form.claim);
    setNoticeType(item.form.noticeType || 'auto');
    setTone(item.form.tone || 'firm');
    setDeadline(item.form.deadline ?? '');
    setCustomRelief(item.form.customRelief || '');
    setResult(item.result);
    setError('');
    setActiveHistoryId(item.id);
  };

  useEffect(() => {
    try {
      const raw = localStorage.getItem(GENERATOR_HISTORY_KEY);
      if (!raw) {
        setHistoryItems([]);
        return;
      }
      const parsed = JSON.parse(raw);
      if (Array.isArray(parsed)) {
        const normalized = parsed.filter(Boolean) as GeneratorHistoryItem[];
        setHistoryItems(normalized);
      }
    } catch {
      setHistoryItems([]);
    }
  }, []);

  useEffect(() => {
    localStorage.setItem(GENERATOR_HISTORY_KEY, JSON.stringify(historyItems));
    onHistoryChange?.(toHistorySummary(historyItems));
  }, [historyItems, onHistoryChange]);

  useEffect(() => {
    onActiveHistoryChange?.(activeHistoryId);
  }, [activeHistoryId, onActiveHistoryChange]);

  useEffect(() => {
    if (!openHistoryRequest?.id) return;
    const target = historyItems.find((item) => item.id === openHistoryRequest.id);
    if (!target) return;
    applyHistoryItem(target);
  }, [openHistoryRequest, historyItems]);

  const pushHistoryItem = (generated: NoticeResponse) => {
    const snapshot: GeneratorFormSnapshot = {
      senderName,
      receiverName,
      relationship,
      facts,
      claim,
      noticeType,
      tone,
      deadline,
      customRelief,
    };
    const createdAt = new Date().toISOString();
    const titleBase = claim.trim() || generated.notice_type_label || 'Generated Legal Notice';
    const item: GeneratorHistoryItem = {
      id: `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
      title: titleBase.length > 72 ? `${titleBase.slice(0, 69)}...` : titleBase,
      created_at: createdAt,
      preview: generated.notice.slice(0, 120).replace(/\s+/g, ' ').trim(),
      form: snapshot,
      result: generated,
    };
    const next = [item, ...historyItems].slice(0, GENERATOR_HISTORY_LIMIT);
    setHistoryItems(next);
    setActiveHistoryId(item.id);
  };

  const addFact = () => setFacts((prev) => [...prev, '']);
  const removeFact = (index: number) => setFacts((prev) => prev.filter((_, i) => i !== index));
  const updateFact = (index: number, value: string) =>
    setFacts((prev) => prev.map((f, i) => (i === index ? value : f)));

  const isFormValid = senderName.trim() && receiverName.trim() && claim.trim() && facts.some((f) => f.trim());

  const handleGenerate = async () => {
    if (!isFormValid) return;
    setIsLoading(true);
    setError('');
    setResult(null);

    try {
      const body: Record<string, unknown> = {
        sender_name: senderName.trim(),
        receiver_name: receiverName.trim(),
        relationship: relationship.trim(),
        facts: facts.filter((f) => f.trim()),
        claim: claim.trim(),
        notice_type: noticeType,
        tone,
      };
      if (deadline) body.custom_deadline = Number(deadline);
      if (customRelief.trim()) {
        body.custom_relief = customRelief
          .split('\n')
          .map((l) => l.trim())
          .filter(Boolean);
      }

      const response = await fetch(`${apiBase}/generate/notice`, {
        method: 'POST',
        headers: authHeaders,
        body: JSON.stringify(body),
      });

      if (!response.ok) throw new Error(`Server responded with ${response.status}`);
      const data: NoticeResponse = await response.json();
      setResult(data);
      pushHistoryItem(data);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Failed to generate notice');
    } finally {
      setIsLoading(false);
    }
  };

  const handleCopy = () => {
    if (!result?.notice) return;
    navigator.clipboard.writeText(result.notice);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const handleDownload = () => {
    if (!result?.notice) return;
    const blob = new Blob([result.notice], { type: 'text/plain;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `legal_notice_${new Date().toISOString().slice(0, 10)}.txt`;
    a.click();
    URL.revokeObjectURL(url);
  };

  const handleReset = () => {
    setSenderName('');
    setReceiverName('');
    setRelationship('');
    setFacts(['']);
    setClaim('');
    setNoticeType('auto');
    setTone('firm');
    setDeadline('');
    setCustomRelief('');
    setResult(null);
    setError('');
    setActiveHistoryId(null);
  };

  const selectedTypeLabel = noticeType === 'auto'
    ? 'Auto-detect'
    : noticeTypes.find((t) => t.id === noticeType)?.label || noticeType;

  return (
    <div className="flex-1 flex h-full bg-surface-container-low overflow-hidden">
      {/* LEFT: Input Form */}
      <div className="w-[480px] flex flex-col border-r border-outline-variant/10 bg-surface">
        <div className="px-6 py-5 border-b border-outline-variant/10">
          <h2 className="text-2xl font-headline font-bold text-primary">Document Generator</h2>
          <p className="text-sm text-on-surface-variant mt-1">
            Generate professional legal notices with AI-powered legal reasoning
          </p>
        </div>

        <div className="flex-1 overflow-y-auto p-6 space-y-5 no-scrollbar">
          {/* Notice Type */}
          <div className="relative">
            <label className="block text-xs font-bold uppercase tracking-[0.15em] text-on-surface-variant mb-2">
              Notice Type
            </label>
            <button
              onClick={() => setShowTypeDropdown(!showTypeDropdown)}
              className="w-full flex items-center justify-between px-4 py-3 bg-surface-container-low border border-outline-variant/20 rounded-xl text-sm text-on-surface hover:border-primary/30 transition"
            >
              <span>{selectedTypeLabel}</span>
              <ChevronDown size={16} className={`transition-transform ${showTypeDropdown ? 'rotate-180' : ''}`} />
            </button>
            <AnimatePresence>
              {showTypeDropdown && (
                <motion.div
                  initial={{ opacity: 0, y: -4 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={{ opacity: 0, y: -4 }}
                  className="absolute z-30 top-full mt-1 w-full bg-white border border-outline-variant/20 rounded-xl shadow-ambient overflow-hidden"
                >
                  <button
                    onClick={() => { setNoticeType('auto'); setShowTypeDropdown(false); }}
                    className={`w-full text-left px-4 py-3 text-sm hover:bg-surface-container-low transition ${noticeType === 'auto' ? 'text-primary font-semibold bg-primary/5' : 'text-on-surface'}`}
                  >
                    ✨ Auto-detect from claim
                  </button>
                  {noticeTypes.map((t) => (
                    <button
                      key={t.id}
                      onClick={() => { setNoticeType(t.id); setShowTypeDropdown(false); }}
                      className={`w-full text-left px-4 py-3 text-sm hover:bg-surface-container-low transition ${noticeType === t.id ? 'text-primary font-semibold bg-primary/5' : 'text-on-surface'}`}
                    >
                      {t.label}
                    </button>
                  ))}
                </motion.div>
              )}
            </AnimatePresence>
          </div>

          {/* Sender & Receiver */}
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="block text-xs font-bold uppercase tracking-[0.15em] text-on-surface-variant mb-2">Sender Name *</label>
              <input
                value={senderName}
                onChange={(e) => setSenderName(e.target.value)}
                placeholder="e.g. Rajesh Kumar"
                className="w-full px-4 py-3 bg-surface-container-low border border-outline-variant/20 rounded-xl text-sm text-on-surface placeholder:text-on-surface-variant/50 focus:ring-2 focus:ring-primary/10 focus:border-primary/30 transition"
              />
            </div>
            <div>
              <label className="block text-xs font-bold uppercase tracking-[0.15em] text-on-surface-variant mb-2">Receiver Name *</label>
              <input
                value={receiverName}
                onChange={(e) => setReceiverName(e.target.value)}
                placeholder="e.g. ABC Pvt Ltd"
                className="w-full px-4 py-3 bg-surface-container-low border border-outline-variant/20 rounded-xl text-sm text-on-surface placeholder:text-on-surface-variant/50 focus:ring-2 focus:ring-primary/10 focus:border-primary/30 transition"
              />
            </div>
          </div>

          {/* Relationship */}
          <div>
            <label className="block text-xs font-bold uppercase tracking-[0.15em] text-on-surface-variant mb-2">Relationship</label>
            <input
              value={relationship}
              onChange={(e) => setRelationship(e.target.value)}
              placeholder="e.g. employee-employer, landlord-tenant"
              className="w-full px-4 py-3 bg-surface-container-low border border-outline-variant/20 rounded-xl text-sm text-on-surface placeholder:text-on-surface-variant/50 focus:ring-2 focus:ring-primary/10 focus:border-primary/30 transition"
            />
          </div>

          {/* Claim */}
          <div>
            <label className="block text-xs font-bold uppercase tracking-[0.15em] text-on-surface-variant mb-2">Claim / Issue *</label>
            <input
              value={claim}
              onChange={(e) => setClaim(e.target.value)}
              placeholder="e.g. unpaid salary for 3 months"
              className="w-full px-4 py-3 bg-surface-container-low border border-outline-variant/20 rounded-xl text-sm text-on-surface placeholder:text-on-surface-variant/50 focus:ring-2 focus:ring-primary/10 focus:border-primary/30 transition"
            />
          </div>

          {/* Facts */}
          <div>
            <div className="flex items-center justify-between mb-2">
              <label className="text-xs font-bold uppercase tracking-[0.15em] text-on-surface-variant">Facts of the Case *</label>
              <button onClick={addFact} className="flex items-center gap-1 text-xs text-primary font-semibold hover:text-primary/80 transition">
                <Plus size={14} /> Add Fact
              </button>
            </div>
            <div className="space-y-2">
              {facts.map((fact, index) => (
                <div key={index} className="flex gap-2">
                  <div className="flex items-center justify-center w-7 h-10 text-xs font-bold text-on-surface-variant/50">{index + 1}.</div>
                  <input
                    value={fact}
                    onChange={(e) => updateFact(index, e.target.value)}
                    placeholder={index === 0 ? 'e.g. Worked from January to March 2024' : 'Add another fact...'}
                    className="flex-1 px-4 py-2.5 bg-surface-container-low border border-outline-variant/20 rounded-xl text-sm text-on-surface placeholder:text-on-surface-variant/50 focus:ring-2 focus:ring-primary/10 focus:border-primary/30 transition"
                  />
                  {facts.length > 1 && (
                    <button onClick={() => removeFact(index)} className="p-2 text-on-surface-variant/40 hover:text-rose-500 transition">
                      <Trash2 size={14} />
                    </button>
                  )}
                </div>
              ))}
            </div>
          </div>

          {/* Tone */}
          <div>
            <label className="block text-xs font-bold uppercase tracking-[0.15em] text-on-surface-variant mb-2">Tone</label>
            <div className="grid grid-cols-3 gap-2">
              {TONE_OPTIONS.map((option) => (
                <button
                  key={option.id}
                  onClick={() => setTone(option.id)}
                  className={`flex flex-col items-center gap-1.5 p-3 rounded-xl border text-xs transition ${
                    tone === option.id
                      ? 'border-primary bg-primary/5 text-primary font-semibold'
                      : 'border-outline-variant/20 text-on-surface-variant hover:border-primary/20'
                  }`}
                >
                  <option.icon size={16} />
                  <span className="font-semibold">{option.label}</span>
                  <span className="text-[10px] opacity-70">{option.description}</span>
                </button>
              ))}
            </div>
          </div>

          {/* Deadline */}
          <div>
            <label className="block text-xs font-bold uppercase tracking-[0.15em] text-on-surface-variant mb-2">
              Custom Deadline (days) <span className="font-normal normal-case tracking-normal text-on-surface-variant/60">— optional</span>
            </label>
            <input
              type="number"
              min={1}
              max={90}
              value={deadline}
              onChange={(e) => setDeadline(e.target.value ? Number(e.target.value) : '')}
              placeholder="Default based on notice type (e.g. 15)"
              className="w-full px-4 py-3 bg-surface-container-low border border-outline-variant/20 rounded-xl text-sm text-on-surface placeholder:text-on-surface-variant/50 focus:ring-2 focus:ring-primary/10 focus:border-primary/30 transition"
            />
          </div>

          {/* Custom Relief */}
          <div>
            <label className="block text-xs font-bold uppercase tracking-[0.15em] text-on-surface-variant mb-2">
              Custom Relief <span className="font-normal normal-case tracking-normal text-on-surface-variant/60">— optional, one per line</span>
            </label>
            <textarea
              value={customRelief}
              onChange={(e) => setCustomRelief(e.target.value)}
              placeholder="e.g.&#10;Pay outstanding salary of ₹3,00,000&#10;Issue experience certificate"
              rows={3}
              className="w-full px-4 py-3 bg-surface-container-low border border-outline-variant/20 rounded-xl text-sm text-on-surface placeholder:text-on-surface-variant/50 focus:ring-2 focus:ring-primary/10 focus:border-primary/30 transition resize-none"
            />
          </div>
        </div>

        {/* Generate Button */}
        <div className="p-6 border-t border-outline-variant/10 space-y-3">
          <button
            onClick={handleGenerate}
            disabled={!isFormValid || isLoading}
            className="w-full flex items-center justify-center gap-2 bg-primary text-white py-4 rounded-xl font-semibold text-sm hover:opacity-90 disabled:opacity-50 transition shadow-xl shadow-primary/20"
          >
            {isLoading ? (
              <>
                <Loader2 size={18} className="animate-spin" />
                Generating Notice (dual-pass)...
              </>
            ) : (
              <>
                <Sparkles size={18} />
                Generate Legal Notice
              </>
            )}
          </button>
          {result && (
            <button
              onClick={handleReset}
              className="w-full py-3 rounded-xl border border-outline-variant/20 text-sm font-semibold text-on-surface-variant hover:bg-surface-container-low transition"
            >
              Reset & Start New
            </button>
          )}
        </div>
      </div>

      {/* RIGHT: Preview */}
      <div className="flex-1 flex flex-col overflow-hidden">
        <AnimatePresence mode="wait">
          {!result && !isLoading && !error ? (
            <motion.div
              key="empty"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              className="flex-1 flex items-center justify-center"
            >
              <div className="text-center space-y-6 max-w-md">
                <div className="w-20 h-20 bg-primary/8 rounded-full flex items-center justify-center text-primary mx-auto">
                  <FileText size={40} strokeWidth={1.5} />
                </div>
                <h3 className="text-3xl font-headline italic text-primary">Legal Notice Generator</h3>
                <p className="text-sm text-on-surface-variant leading-relaxed">
                  Fill in the structured form on the left with your case details. The AI will generate a
                  professional legal notice using applicable Indian laws, dual-pass refinement, and RAG-powered
                  legal context.
                </p>
                <div className="flex flex-wrap justify-center gap-2 text-[11px] font-label font-bold uppercase tracking-[0.15em] text-on-surface-variant/60">
                  <span className="px-3 py-1.5 bg-surface-container rounded-full">FIRAC Structure</span>
                  <span className="px-3 py-1.5 bg-surface-container rounded-full">Dual-Pass AI</span>
                  <span className="px-3 py-1.5 bg-surface-container rounded-full">RAG Context</span>
                  <span className="px-3 py-1.5 bg-surface-container rounded-full">9 Notice Types</span>
                </div>
              </div>
            </motion.div>
          ) : isLoading ? (
            <motion.div
              key="loading"
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              className="flex-1 flex items-center justify-center"
            >
              <div className="text-center space-y-6">
                <div className="relative w-20 h-20 mx-auto">
                  <div className="absolute inset-0 border-4 border-primary/10 rounded-full" />
                  <div className="absolute inset-0 border-4 border-primary border-t-transparent rounded-full animate-spin" />
                  <div className="absolute inset-3 border-4 border-primary/20 border-b-transparent rounded-full animate-spin" style={{ animationDirection: 'reverse', animationDuration: '1.5s' }} />
                </div>
                <div>
                  <h3 className="text-xl font-headline text-primary">Generating Legal Notice</h3>
                  <p className="text-sm text-on-surface-variant mt-2">
                    Pass 1: Drafting → Pass 2: Refining legal language...
                  </p>
                </div>
              </div>
            </motion.div>
          ) : error ? (
            <motion.div
              key="error"
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0 }}
              className="flex-1 flex items-center justify-center p-8"
            >
              <div className="bg-rose-50 border border-rose-200 rounded-2xl p-8 max-w-md text-center">
                <AlertCircle size={40} className="text-rose-500 mx-auto mb-4" />
                <h3 className="text-lg font-semibold text-rose-900">Generation Failed</h3>
                <p className="text-sm text-rose-700 mt-2">{error}</p>
                <button
                  onClick={() => setError('')}
                  className="mt-4 px-6 py-2 bg-rose-100 text-rose-800 rounded-xl text-sm font-semibold hover:bg-rose-200 transition"
                >
                  Dismiss
                </button>
              </div>
            </motion.div>
          ) : result ? (
            <motion.div
              key="result"
              initial={{ opacity: 0, y: 10 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0 }}
              className="flex-1 flex flex-col overflow-hidden"
            >
              {/* Result Header */}
              <div className="px-8 py-5 border-b border-outline-variant/10 bg-surface flex items-center justify-between">
                <div className="flex items-center gap-4">
                  <div className={`px-3 py-1.5 rounded-full border text-xs font-bold ${CONFIDENCE_COLORS[result.confidence_label] || CONFIDENCE_COLORS.medium}`}>
                    Confidence: {Math.round(result.confidence * 100)}%
                  </div>
                  <span className="text-xs text-on-surface-variant">
                    Type: <strong className="text-on-surface">{result.notice_type_label}</strong>
                  </span>
                  <span className="text-xs text-on-surface-variant">
                    Laws: <strong className="text-on-surface">{result.laws_used.length}</strong>
                  </span>
                </div>
                <div className="flex items-center gap-2">
                  <button
                    onClick={handleCopy}
                    className="flex items-center gap-2 px-4 py-2 rounded-xl border border-outline-variant/20 text-xs font-semibold text-on-surface hover:border-primary/30 hover:bg-primary/5 transition"
                  >
                    {copied ? <CheckCircle2 size={14} className="text-emerald-600" /> : <Copy size={14} />}
                    {copied ? 'Copied!' : 'Copy'}
                  </button>
                  <button
                    onClick={handleDownload}
                    className="flex items-center gap-2 px-4 py-2 rounded-xl bg-primary text-white text-xs font-semibold hover:opacity-90 transition shadow-lg shadow-primary/20"
                  >
                    <Download size={14} />
                    Download .txt
                  </button>
                </div>
              </div>

              {/* Notice Content */}
              <div className="flex-1 overflow-y-auto p-8 no-scrollbar">
                <motion.div
                  initial={{ opacity: 0, y: 10 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ delay: 0.1 }}
                  className="max-w-3xl mx-auto"
                >
                  {/* Notice Preview Card */}
                  <div className="bg-white rounded-2xl border border-outline-variant/15 shadow-ambient overflow-hidden">
                    <div className="bg-primary/[.03] px-8 py-4 border-b border-outline-variant/10">
                      <div className="flex items-center gap-3">
                        <FileText size={18} className="text-primary" />
                        <span className="text-xs font-bold uppercase tracking-[0.2em] text-primary/70">Generated Legal Notice</span>
                      </div>
                    </div>
                    <div className="px-8 py-6 text-on-surface text-sm leading-relaxed font-body markdown-body whitespace-pre-wrap">
                      <Markdown components={markdownComponents}>{result.notice}</Markdown>
                    </div>
                  </div>

                  {/* Laws Used */}
                  {result.laws_used.length > 0 && (
                    <motion.div
                      initial={{ opacity: 0, y: 10 }}
                      animate={{ opacity: 1, y: 0 }}
                      transition={{ delay: 0.2 }}
                      className="mt-6 bg-white rounded-2xl border border-outline-variant/15 p-6"
                    >
                      <div className="text-xs font-bold uppercase tracking-[0.2em] text-primary/70 mb-3">
                        Authorities Relied Upon
                      </div>
                      <div className="flex flex-wrap gap-2">
                        {result.laws_used.map((law, i) => (
                          <span
                            key={i}
                            className="inline-block px-3 py-1.5 bg-surface-container-low rounded-lg text-xs font-semibold text-on-surface border border-outline-variant/10"
                          >
                            {law}
                          </span>
                        ))}
                      </div>
                    </motion.div>
                  )}

                  {/* Metadata */}
                  <motion.div
                    initial={{ opacity: 0 }}
                    animate={{ opacity: 1 }}
                    transition={{ delay: 0.3 }}
                    className="mt-4 flex flex-wrap gap-x-6 gap-y-2 text-[11px] text-on-surface-variant/60 px-2"
                  >
                    <span>Tone: {result.meta?.tone as string || tone}</span>
                    <span>Deadline: {(result.meta?.deadline_days as number) || 15} days</span>
                    <span>Heuristics: {(result.meta?.heuristics_matched as number) || 0} matched</span>
                    <span>RAG: {result.meta?.has_retrieval_context ? 'Active' : 'None'}</span>
                  </motion.div>
                </motion.div>
              </div>
            </motion.div>
          ) : null}
        </AnimatePresence>
      </div>
    </div>
  );
};
